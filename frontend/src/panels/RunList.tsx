import { Fragment, MouseEvent, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { BLOCKED, usePopupWindow } from './popupWindow';
import { api, bytes, Json, short } from '../api';
import { LIVE_STATES } from './RunControl';
import { FolderMoveBar, Folders, useFolders } from './Folders';
import { childrenOf, historyOf, startedFrom } from '../lineage';
import { OPEN_RUNS, openTasksAt, RunsAt } from '../openAt';

/** Which run the bottom tabs show (user request 2026-09-21): ONE button at the right end of the bottom tab strip, where
 *  the drop-down list of runs used to be. It only reads "Runs..."; the run that is shown is named as plain text to its
 *  LEFT. Pressing it opens the run window - a browser window of its own, drawn through a portal like the connection
 *  window - with every run under the output folder as a table: when it started and finished, how long it worked, and
 *  what it was and came to. A double click on a row shows that run; "Details" adds the rest; "Clear" shows no run.
 *  Choosing a task in the Project column shows that task's newest run, or none (App.tsx, record 7.212).
 *
 *  Nothing here updates on a timer: the list is read when the button is pressed and by "Refresh list", a run's details
 *  when they are opened. So a run that is working shows the state and duration AS OF the read time, which is printed.
 *
 *  Folders (record 7.263, plan "Categories for runs and models"), as the Tasks window has them: All runs, Unfiled and the
 *  user's folders on the left, runs ticked and moved with "Move to...". Organization only: a run is never moved on disk.
 *
 *  Relationships (record 7.264, plan "Runs window"): "Started from" and "Saved model" columns, and in Details where the run's
 *  model came from and what came of it, with a folded history. Every run named is a link that shows it here - selected,
 *  scrolled to, its Details open - and its task opens the Tasks window at the task. Other windows open this one AT a run, or
 *  filtered to one task's runs (openAt.ts): following a link changes no draft, no shown run and no running job. */

const two = (n: number) => String(n).padStart(2, '0');
/** Local time, in a form that sorts and compares by eye: 2026-09-21 14:03:22. */
const stamp = (utc?: string | null) => {
  const d = utc ? new Date(utc) : null;
  return d && !Number.isNaN(d.getTime()) ? `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}` : null;
};
const span = (seconds?: number | null) => {
  if (seconds == null) return null;
  if (seconds < 59.95) return `${seconds.toFixed(1)} s`;
  const t = Math.round(seconds), h = Math.floor(t / 3600);
  return h ? `${h} h ${two(Math.floor(t % 3600 / 60))} min` : `${Math.floor(t / 60)} min ${two(t % 60)} s`;
};
const pairs = (values: Json) => Object.entries(values ?? {}).map(([k, v]) => `${k}=${short(v)}`).join('  ');
// A best design lists its variables as [{ variable_id, value, unit }].
const variables = (list: Json) => Array.isArray(list) ? list.map((v: Json) => `${v.variable_id}=${short(v.value)}${v.unit ? ` ${v.unit}` : ''}`).join('  ') : pairs(list);
const folder = (runDir: string) => runDir.split(/[\\/]/).filter(Boolean).pop() ?? runDir;
const isLive = (r: Json) => LIVE_STATES.includes(r.state);
const taskOf = (r: Json) => r.task_name ?? String(r.task_id ?? 'unknown task').split(':')[0];
// `state`: what the page's own status poll says now - the list row keeps the state of its last read ("starting").
const label = (r: Json, state?: string | null) => `${stamp(r.created_utc) ?? 'unknown time'} | ${taskOf(r)} | ${r.mode} seed${r.seed} | ${state ?? r.state ?? 'not started'}${r.mock ? ' [MOCK]' : ''}`;
const STATE_CSS: Record<string, string> = { completed: 'ok', running: 'busy', starting: 'busy', pausing: 'busy', stopping: 'busy', paused: 'not_ready',
  interrupted: 'not_ready', failed: 'failed', cancelled: 'unknown', stopped: 'unknown' };
const RESUME: Record<string, string> = { full_state: 'yes', weights_only: 'model only', none: 'no' };

/** The "Finished" cell. A run at rest has the end of its last segment; a run that is working has none; a worker that
 *  died wrote none, so the last sign of life is what is known. */
function finished(r: Json): { text: string; css?: string; title?: string } {
  if (isLive(r)) return { text: 'still running', css: 'ok' };
  if (r.ended_utc) return r.state === 'paused' ? { text: `${stamp(r.ended_utc)} (paused)`, title: 'Paused, not finished: this is when the pause was complete. The run can continue.' } : { text: stamp(r.ended_utc)! };
  if (r.state === 'interrupted' && r.last_seen_utc) return { text: `last seen ${stamp(r.last_seen_utc)}`, css: 'warn',
    title: 'The worker process went away without a clean end, so no finish time was written. This is its last sign of life.' };
  return { text: '-' };
}

type Column = { key: string; title: string; help: string; value?: (r: Json, byDir: Map<string, Json>) => string | number | null };
const COLUMNS: Column[] = [
  { key: 'started', title: 'Started', help: 'When the run was created (local time of this computer).', value: r => r.created_utc ?? null },
  { key: 'finished', title: 'Finished', help: 'When the run came to rest: completed, stopped, failed or paused. A run that is working has no finish time yet.', value: r => (isLive(r) ? null : r.ended_utc ?? r.last_seen_utc ?? null) },
  { key: 'duration', title: 'Duration', help: 'How long the run was actually working. The time it sat paused is not counted; "Details" shows it.', value: r => r.active_seconds ?? null },
  { key: 'state', title: 'State', help: 'How the run stands, and under it why it stopped.', value: r => r.state ?? '' },
  { key: 'task', title: 'Task', help: 'The task (circuit and its targets) the run optimizes.', value: r => taskOf(r) },
  { key: 'mode', title: 'Mode', help: 'scratch = from random weights; fine_tune / frozen / resume = from a saved model.', value: r => r.mode ?? '' },
  { key: 'from', title: 'Started from', help: 'Where the run\'s model came from: "template GT" = a new model made from an encoder\'s template; "ota7t (2) @ 420" = the saved model it loaded and the save point (its evaluations), a link to that run; "offline: 22 runs" = a model trained offline on recorded runs; "-" = a baseline or a calibration, which loads none.',
    value: (r, byDir) => startedFrom(r, byDir).text },
  { key: 'model', title: 'Saved model', help: 'The name of the RL model this run saves; every model under the output folder has one of its own, so a name already given gets a number. Empty for a run that saves none (a baseline, LLM only).', value: r => r.model_label ?? null },
  { key: 'seed', title: 'Seed', help: 'The random seed of the run.', value: r => r.seed ?? null },
  { key: 'evaluations', title: 'Evaluations', help: 'Candidate designs simulated so far, of the budget the run was given.', value: r => r.evaluations ?? null },
  { key: 'feasible', title: 'First feasible', help: 'How many evaluations had been spent when the first design met every target. "none" = no design has met them.', value: r => r.first_feasible_eval_count ?? null },
  { key: 'experiment', title: 'Experiment', help: 'The experiment folder the run belongs to.', value: r => r.experiment ?? '' },
  { key: 'data', title: 'Data', help: 'MOCK = the built-in synthetic backend, not a circuit result. real = Virtuoso / Spectre simulations.', value: r => (r.mock ? 'mock' : 'real') },
  { key: 'resume', title: 'Can continue', help: 'Whether the saved state allows this run to be continued: yes (full state), model only (usable for fine_tune / frozen - also a full save point written by an older version of the optimizer code, which only that version can continue), no - also when the run folder no longer holds its save point (a copy made without them, or deleted ones).', value: r => r.resumability ?? '' },
];

/** Where this run's model came from and what came of it (record 7.264). From the run list's own fields (lineage.ts): a
 *  run is named by its run folder, never inferred from a name. `tasks`: the registered tasks, for "saved again since". */
function Relationships({ row, info, runs, byDir, tasks, from, onFocus }: { row: Json; info: Json; runs: Json[]; byDir: Map<string, Json>;
  tasks: Map<string, Json>; from: Window | null; onFocus: (dir: string) => void }) {
  const origin = startedFrom(row, byDir);
  const task = row.task_key ? tasks.get(row.task_key) ?? null : null;
  const savedSince = !!task?.saved_utc && !!row.created_utc && Date.parse(task.saved_utc) > Date.parse(row.created_utc);
  const children = childrenOf(row, runs), history = historyOf(row, byDir);
  const sources: Json[] = info?.manifest?.pretraining?.sources ?? [];
  const behind = history.steps.length - 1;
  const runLink = (dir: string, text: string) => byDir.has(dir)
    ? <button className="item-link" onClick={() => onFocus(dir)} title={`${dir}\nShow this run here: selected, its Details open.`}>{text}</button>
    : <span title={dir}>{text} <span className="hint">(not under this output folder)</span></span>;
  const stepText = (s: Json) => `${s?.task_key ?? (s ? taskOf(s) : '?')} · ${s?.mode ?? '?'} · ${s?.evaluations ?? '?'} evaluations${s?.model_label ? ` · ${s.model_label}` : ''}`;
  return (<table className="grid small run-relations"><tbody>
    <tr><td>Task</td><td>{row.task_key ? <button className="item-link" onClick={() => openTasksAt({ task_key: row.task_key, from })}
        title="Open the Tasks window at this task.">{row.task_key}</button> : taskOf(row)}
      {row.task_definition_hash && <span className="hint"> · definition {String(row.task_definition_hash).slice(0, 12)}</span>}
      {task?.revision != null && <span className="hint"> · revision {task.revision} now</span>}
      {savedSince && <span className="warn"> · saved again since this run ({stamp(task.saved_utc)})</span>}
      {row.task_key && tasks.size > 0 && !task && <span className="hint"> · no longer registered</span>}</td></tr>
    <tr><td>Started from</td><td>{row.run_kind === 'offline_pretraining'
        ? <>trained offline on {row.pretraining_sources ?? sources.length} recorded runs
            {sources.length > 0 && <details className="more"><summary>the recorded runs</summary><ul className="steps-list">{sources.map((s: Json) =>
              <li key={s.run_dir}>{runLink(s.run_dir, `${s.task ?? '?'} · ${s.evaluations ?? '?'} evaluations · ${folder(s.run_dir)}`)}</li>)}</ul></details>}</>
        : origin.parent ? <>{runLink(origin.parent, origin.text)}{row.parent?.checkpoint_id
            && <span className="hint">{` (${row.parent.relation === 'frozen' ? 'evaluated' : 'fine-tuned'} from its save point ${row.parent.checkpoint_id})`}</span>}</>
        : origin.text === '-' ? <span className="hint">no model: {row.run_kind === 'calibration' ? 'a calibration' : 'a baseline simulation'} loads none</span>
        : <>{origin.text} <span className="hint">(a new model)</span></>}</td></tr>
    <tr><td>Saved model</td><td>{row.model_label ? <>{row.model_label}{info && <span className="hint"> · latest save point {info.save_point ?? 'none'}</span>}</>
      : <span className="hint">none</span>}</td></tr>
    <tr><td>Runs that started from its model</td><td>{children.length ? children.map((c, i) => <Fragment key={c.run_dir}>{i > 0 && ', '}
      {runLink(c.run_dir, `${stamp(c.created_utc) ?? folder(c.run_dir)} ${c.mode}${c.model_label ? ` (${c.model_label})` : ''}`)}</Fragment>)
      : <span className="hint">none under this output folder</span>}</td></tr>
    <tr><td>History</td><td><details className="more run-history"><summary>{behind ? `${behind} model${behind > 1 ? 's' : ''} behind this run, oldest first` : 'no saved model behind this run'}</summary>
      <ol className="steps-list"><li className={history.root.missing ? 'warn' : 'hint'}>{history.root.text}</li>
        {history.steps.map(s => <li key={s.run_dir}>{s.run_dir === row.run_dir ? <b>this run</b> : runLink(s.run_dir, stepText(s.row))}
          {s.checkpoint_id && <span className="hint"> - loaded the one above at its save point {s.checkpoint_id}</span>}</li>)}</ol></details></td></tr>
  </tbody></table>);
}

/** Everything else about one run. `row` is its line of the list; `info` is /api/runs/status, read when the details open. */
function RunDetails({ row, info, error, onCopy, copied, relations }: { row: Json; info: Json; error?: string; onCopy: (text: string) => void; copied: boolean;
  relations: JSX.Element }) {
  const b = info?.budget, best = info?.best_design, first = info?.first_feasible, summary = info?.summary, source = info?.manifest?.source_model;
  const facts: [string, string | null | undefined][] = [
    ['Run id', row.run_id], ['Registered task', row.task_key], ['Task id', row.task_id], ['Experiment', row.experiment],
    ['Created', stamp(row.created_utc)], ['Worker began', stamp(row.started_utc)], ['Came to rest', stamp(row.ended_utc)], ['Last sign of life', row.ended_utc ? null : stamp(row.last_seen_utc)],
    ['Worked for', span(row.active_seconds)], ['Paused between segments', row.paused_seconds ? span(row.paused_seconds) : null],
    ['Summed simulator job time', summary?.time?.sum_job_runtime_seconds != null ? `${span(summary.time.sum_job_runtime_seconds)} (parallel jobs added up: not elapsed time)` : null],
    ['Stop reason', row.stop_reason], ['Error', row.error],
    ['Budget', b ? `${b.charged} charged / ${b.max_evaluations} (completed ${b.completed}, failed ${b.failed}, in flight ${b.in_flight}, remaining ${b.remaining})` : null],
    ['Spectre launches', b ? `${b.launches}${b.max_launches ? ' / ' + b.max_launches : ''} (retries ${b.retries}, cache hits ${b.cache_hits})` : null],
    ['Learner updates', info ? String(info.learner_updates ?? 0) : null],
    ['First feasibility', info ? (first ? `at ${first.first_feasible_eval_count} evaluations charged (${first.completed_count} completed, ${first.spectre_launches} launches)` : 'not reached') : null],
    ['Best design', info ? (best ? `${best.feasible ? 'FEASIBLE' : 'infeasible'}  ${pairs(best.metrics)}  violation ${short(best.violation)}` : 'none') : null],
    ['Best design variables', best?.variables ? variables(best.variables) : null],
    ['Model loaded at the start', info ? (source?.run_id ? `run ${String(source.run_id).slice(0, 12)} / ${source.checkpoint_id}` : 'none (random weights)') : null],
    ['Last model save', info ? stamp(info.last_checkpoint_utc) ?? 'none' : null],
    // a save point the summary names but the run folder no longer holds (a copy made without them, deleted ones): said (7.215)
    ['Saved state', summary?.output ? (info?.save_point === null && summary.output.resumability !== 'none'
      ? `none: the run's summary names its save point ${summary.output.latest_checkpoint ?? ''} as ${summary.output.resumability}, but the run folder no longer holds it (a copy made without its save points, or they were deleted); nothing to continue from`
      // a full save point of an older optimizer source: only that source can continue it (record 7.221)
      : info?.save_point_code === 'older' && summary.output.resumability === 'full_state'
      ? `model only: the latest save ${summary.output.latest_checkpoint ?? ''} is a full save point written by an older version of the optimizer code - only that version can continue it; fine-tune and frozen still load its model`
      : `${summary.output.resumability} (${summary.output.completeness} output, latest save ${summary.output.latest_checkpoint ?? 'none'})`) : null],
    ['Parallel simulations', info?.concurrency ? `${info.concurrency}` : null],
    ['Connection', info?.connection_profile_id ?? (info ? 'none (not needed)' : null)],
    ['Data written', info?.bytes_written != null ? bytes(info.bytes_written) : null],
  ];
  return (<div className="run-details">
    {error && <p className="error">The details of this run could not be read: {error}</p>}
    {!info && !error && <p className="hint">Reading the run's details...</p>}
    <h4>Relationships</h4>
    {relations}
    <table className="grid small run-facts"><tbody>
      <tr><td>Run folder</td><td className="path" title="Click to copy" onClick={() => onCopy(row.run_dir)}>{row.run_dir}{copied && <b className="ok"> copied</b>}</td></tr>
      {facts.filter(([, value]) => value != null && value !== '').map(([name, value]) => <tr key={name}><td>{name}</td><td className={name === 'Error' ? 'error' : ''}>{value}</td></tr>)}
    </tbody></table>
    {row.segments?.length > 0 && <>
      <h4>Segments <span className="hint">- one per Start or Resume; a pause lies between two of them</span></h4>
      <table className="grid small run-segments"><thead><tr><th>#</th><th>Began as</th><th>Started</th><th>Ended</th><th>Ended as</th><th>Why</th><th>Worked for</th></tr></thead>
        <tbody>{row.segments.map((s: Json) => <tr key={s.segment}><td>{s.segment}</td><td>{s.entry}</td><td>{stamp(s.started_utc) ?? 'not begun'}</td><td>{stamp(s.ended_utc) ?? (s.started_utc ? 'open' : '-')}</td>
          <td>{s.end_state ?? '-'}</td><td>{s.stop_reason ?? '-'}</td><td className="numeric">{span(s.active_seconds) ?? '-'}</td></tr>)}</tbody></table></>}
  </div>);
}

export function RunListButton({ runs, runsError, runDir, status, onChoose, onRefresh }: { runs: Json[]; runsError: string | null; runDir: string | null;
  status: Json; onChoose: (runDir: string | null) => void; onRefresh: () => Promise<Json[]> }) {
  // While `popup` is set, the run window is open (one pop-up window for the whole page: `popupWindow.ts`).
  const { popup, root, blocked, open: openPopup } = usePopupWindow('gator-runs',
    { title: 'GATOR - runs', features: 'popup,width=1500,height=860', rootId: 'runs-root' });
  const [loading, setLoading] = useState(false);
  const [readAt, setReadAt] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [sort, setSort] = useState<{ key: string; down: boolean }>({ key: 'started', down: true });
  const [open, setOpen] = useState<string | null>(null);        // the run whose details are shown
  const [info, setInfo] = useState<{ dir: string; value?: Json; error?: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const folders = useFolders('runs');
  const [selected, setSelected] = useState<string[]>([]);
  const [onlyTask, setOnlyTask] = useState<string | null>(null);   // only one task's runs: a link from the Tasks window (7.264)
  const [tasks, setTasks] = useState<Map<string, Json>>(new Map());
  const [focus, setFocus] = useState<string | null>(null);         // a run to scroll to once it is drawn
  const byDir = useMemo(() => new Map(runs.map(r => [r.run_dir, r])), [runs]);
  const readTasks = () => api.tasks().then(read => setTasks(new Map((read.tasks ?? []).map((x: Json) => [x.task_key, x]))), () => undefined);
  const chooseFolder = (id: string) => { folders.setFolder(id); setSelected([]); setOpen(null); };
  const select = (dir: string, checked: boolean) => setSelected(dirs => checked ? [...dirs.filter(d => d !== dir), dir] : dirs.filter(d => d !== dir));
  const move = async (id: string) => { if (await folders.move(selected, id)) setSelected([]); };

  const readDetails = (dir: string) => { setInfo({ dir }); api.status(dir).then(value => setInfo(i => (i?.dir === dir ? { dir, value } : i)), e => setInfo(i => (i?.dir === dir ? { dir, error: e.message } : i))); };
  const refresh = () => { setLoading(true); setSelected([]); void folders.refresh(); void readTasks(); onRefresh().finally(() => setLoading(false)); if (open) readDetails(open); };
  /** Show one run in this window: every folder, no filter, its Details open, scrolled to. */
  const focusRun = (dir: string) => {
    folders.setFolder('all'); setFilter(''); setSelected([]);
    setOnlyTask(task => (task && byDir.get(dir)?.task_key !== task ? null : task));
    setOpen(dir); readDetails(dir); setFocus(dir);
  };
  // Whoever had the list read - this window, or the page when a run was started - the window says when that was.
  useEffect(() => setReadAt(new Date().toLocaleTimeString([], { hour12: false })), [runs]);
  const toggle = (dir: string) => { if (open === dir) { setOpen(null); return; } setOpen(dir); readDetails(dir); };
  // A double click on a run's row shows that run in the bottom tabs (user request 2026-09-21: no "Show" column). Not when it
  // lands on the row's "Details" button: that only opens and closes the details. The word the double click selected is let go.
  const showRun = (e: MouseEvent<HTMLTableRowElement>, dir: string) => {
    if ((e.target as HTMLElement).closest('button, input, select, label')) return;
    (popup ?? window).getSelection()?.removeAllRanges();
    onChoose(dir);
  };

  const openWindow = (from?: Window | null) => {
    refresh();                                                   // pressing the button is the request to see the current list
    openPopup(from);
  };
  // Another window's link (openAt.ts): this window opens AT a run, or with one task's runs only.
  const latest = useRef({ openWindow, focusRun });
  latest.current = { openWindow, focusRun };
  useEffect(() => {
    const show = (event: Event) => {
      const at = (event as CustomEvent<RunsAt>).detail ?? {};
      latest.current.openWindow(at.from);
      if (at.run_dir) { latest.current.focusRun(at.run_dir); if (at.task_key) setOnlyTask(at.task_key); }
      else if (at.task_key) { folders.setFolder('all'); setFilter(''); setSelected([]); setOpen(null); setOnlyTask(at.task_key); }
    };
    window.addEventListener(OPEN_RUNS, show);
    return () => window.removeEventListener(OPEN_RUNS, show);
  }, []);
  useEffect(() => {
    if (!focus || !popup) return;
    const row = [...popup.document.querySelectorAll<HTMLTableRowElement>('table.run-table tbody > tr')].find(tr => tr.title === focus);
    if (row) { row.scrollIntoView({ block: 'center' }); setFocus(null); }
  });
  // The click happens in the run window, so ITS clipboard is the one a browser lets this gesture write to.
  const copyPath = (text: string) => (popup ?? window).navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }, () => undefined);

  const current: Json = runs.find(r => r.run_dir === runDir) ?? null;
  const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
  const text = (r: Json) => [stamp(r.created_utc), stamp(r.ended_utc), taskOf(r), r.task_key, r.task_id, r.mode, r.model_label, `seed${r.seed}`, r.state, r.stop_reason, r.experiment, r.mock ? 'mock' : 'real', folder(r.run_dir),
    folders.data.folders[folders.of(r.run_dir)]].join(' ').toLowerCase();
  const column = COLUMNS.find(c => c.key === sort.key) ?? COLUMNS[0];
  // Empty cells stay at the bottom whichever way the column is sorted. Only while the window is open: the page redraws
  // on every status poll, and a closed window needs no sorted list.
  const shown = !popup ? [] : runs.filter(r => folders.holds(r.run_dir) && (!onlyTask || r.task_key === onlyTask) && words.every(w => text(r).includes(w))).sort((a, b) => {
    const x = column.value!(a, byDir), y = column.value!(b, byDir);
    if (x == null || x === '' || y == null || y === '') return (x == null || x === '' ? 1 : 0) - (y == null || y === '' ? 1 : 0);
    return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))) * (sort.down ? -1 : 1);
  });
  const timed = runs.some(r => 'active_seconds' in r);     // an older workbench server lists runs without their times

  const view = popup && root && (
    <div className="run-window">
      <h2>Runs</h2>
      <div className="row">
        <button onClick={refresh} disabled={loading || folders.busy}>Refresh list</button>
        <button onClick={() => onChoose(null)} disabled={!runDir} title="The bottom tabs of the workbench show no run. Nothing is stopped or deleted.">Clear</button>
        <input className="run-filter" placeholder="Filter: task, mode, state, mock / real, date ..." value={filter} onChange={e => { setFilter(e.target.value); setSelected([]); }} />
        <span className="hint run-count">{loading ? 'Reading the runs...' : runsError ? 'The list could not be read.'
          : `${runs.length} run${runs.length === 1 ? '' : 's'} under the output folder${readAt ? `, read at ${readAt}` : ''}. Nothing here updates by itself.`}</span>
      </div>
      {runsError && !loading && <p className="error run-list-error">The run list could not be read: {runsError}</p>}
      {folders.error && <p className="error" role="alert">{folders.error} Press Refresh list to retry.</p>}
      <p className="hint"><b>Double click</b> a run to show it in the bottom tabs of the workbench (Run status, Logs, Data tables, Output files); the run that is shown is marked. <b>Clear</b> shows no run. Choosing a task under <b>Task</b> shows its newest run, or none if it has none. This window stays open until you close it.</p>
      <details className="more"><summary>What the columns mean</summary>
        <ul className="steps-list">{COLUMNS.map(c => <li key={c.key}><b>{c.title}</b>: {c.help}</li>)}
          <li>All times are the local time of this computer. Press a column title to sort by it. "Details" shows everything else the run recorded.</li></ul></details>
      {runs.length > 0 && !timed && <p className="warn">The workbench server that is running is older than this page and does not report when a run finished or how long it took.
        Restart it (Ctrl+C in its terminal, then start `serve` again) and press "Refresh list".</p>}
      {runs.length === 0 && !loading && !runsError && <p className="hint run-empty">No run yet under this output folder. A run appears here as soon as it has been started.</p>}
      <div className="task-browser">
      <Folders state={folders} keys={runs.map(r => r.run_dir)} popup={popup} onSelect={chooseFolder} />
      <div className="task-folder-content">
      <FolderMoveBar state={folders} shown={shown.length} selected={selected.length} onMove={id => void move(id)} />
      {onlyTask && <p className="hint run-only-task">Only the runs of <code>{onlyTask}</code>{' '}
        <button className="item-link" onClick={() => setOnlyTask(null)}>Show every run</button></p>}
      {runs.length > 0 && <div className="scroll"><table className="grid run-table">
        <thead><tr>
          <th className="task-select"><input type="checkbox" aria-label="Select all shown runs" disabled={folders.busy || !folders.ready || !shown.length}
            checked={shown.length > 0 && shown.every(r => selected.includes(r.run_dir))}
            ref={input => { if (input) input.indeterminate = selected.length > 0 && !shown.every(r => selected.includes(r.run_dir)); }}
            onChange={e => setSelected(e.target.checked ? shown.map(r => r.run_dir) : [])} /></th>
          {COLUMNS.map(c => <th key={c.key} className="sortable" title={`${c.help} Press to sort.`} aria-sort={sort.key === c.key ? (sort.down ? 'descending' : 'ascending') : undefined}
            onClick={() => setSort(s => ({ key: c.key, down: s.key === c.key ? !s.down : true }))}>{c.title}{sort.key === c.key && <span className="sort-mark">{sort.down ? ' ▼' : ' ▲'}</span>}</th>)}
          <th className="plain"></th></tr></thead>
        <tbody>{shown.map(r => { const active = r.run_dir === runDir, end = finished(r), origin = startedFrom(r, byDir); return (<Fragment key={r.run_dir}>
          <tr className={active ? 'current' : ''} aria-current={active ? 'true' : undefined} title={r.run_dir} onDoubleClick={e => showRun(e, r.run_dir)}>
            <td className="task-select"><input type="checkbox" aria-label={`Select ${folder(r.run_dir)}`} checked={selected.includes(r.run_dir)}
              disabled={folders.busy || !folders.ready} onChange={e => select(r.run_dir, e.target.checked)} /></td>
            <td className="wrap-words">{stamp(r.created_utc) ?? '-'}{folders.folder === 'all' && folders.data.folders[folders.of(r.run_dir)]
              && <div className="hint task-folder-label">{folders.data.folders[folders.of(r.run_dir)]}</div>}</td>
            <td className={`wrap-words${end.css ? ` ${end.css}` : ''}`} title={end.title}>{end.text}</td>
            <td className="numeric" title={r.paused_seconds ? `Working time. It also sat paused for ${span(r.paused_seconds)}.` : undefined}>{span(r.active_seconds) ?? '-'}{isLive(r) && r.active_seconds != null && ' so far'}</td>
            <td><span className={`badge state-${STATE_CSS[r.state] ?? 'unknown'}`}>{r.state ?? 'not started'}</span>{r.stop_reason && <div className="hint">{r.stop_reason}</div>}</td>
            <td className="wrap" title={r.task_id}>{taskOf(r)}</td><td>{r.mode}</td>
            <td className="wrap">{origin.parent ? <button className="item-link" onClick={() => focusRun(origin.parent!)} title={`${origin.parent}\nShow the run it started from.`}>{origin.text}</button> : origin.text}
              {origin.missing && <span className="hint" title="That run is not under this output folder."> (gone)</span>}</td>
            <td className="wrap">{r.model_label ?? '-'}</td><td className="numeric">{r.seed}</td>
            <td className="numeric">{r.evaluations ?? '-'}{r.max_evaluations != null && ` / ${r.max_evaluations}`}</td>
            <td className="numeric">{r.first_feasible_eval_count != null ? `at ${r.first_feasible_eval_count}` : r.evaluations != null ? 'none' : '-'}</td>
            <td className="wrap">{r.experiment}</td>
            <td>{r.mock ? <span className="badge model-tag mock-tag">MOCK</span> : 'real'}</td>
            <td>{RESUME[r.resumability] ?? '-'}</td>
            <td><button className="notes-link" aria-expanded={open === r.run_dir} onClick={() => toggle(r.run_dir)}>{open === r.run_dir ? 'Hide details' : 'Details'}</button></td>
          </tr>
          {open === r.run_dir && <tr className="run-details-row"><td colSpan={COLUMNS.length + 2}>
            <RunDetails row={r} info={info?.dir === r.run_dir ? info?.value : null} error={info?.dir === r.run_dir ? info?.error : undefined} onCopy={copyPath} copied={copied}
              relations={<Relationships row={r} info={info?.dir === r.run_dir ? info?.value : null} runs={runs} byDir={byDir} tasks={tasks} from={popup} onFocus={focusRun} />} /></td></tr>}
        </Fragment>); })}</tbody></table></div>}
      {runs.length > 0 && shown.length === 0 && <p className="hint task-folder-empty">{filter ? 'No run matches the filter in this folder.' : 'This folder is empty. Select runs in All runs, then use Move to…'}</p>}
      </div></div>
    </div>
  );

  return (<>
    {blocked && <span className="error run-list-blocked">{BLOCKED}</span>}
    {/* The run that is shown is said as plain text to the LEFT of the button; the button itself only reads "Runs..." (user request 2026-09-21). */}
    <span className="run-list-current" title={runDir ?? undefined}>{current ? label(current, status?.run_dir === runDir ? status.state : null) : runDir ? folder(runDir) : 'No run selected'}</span>
    <button className={`run-list-button${popup ? ' open' : ''}`} onClick={() => openWindow()}
      title={popup ? 'The run window is open: press to bring it to the front and read the list again.' : 'Opens the run window: every run with its start and finish time, its duration and its results. Choose there which run these tabs show.'}>Runs...</button>
    {view && createPortal(view, root!)}
  </>);
}
