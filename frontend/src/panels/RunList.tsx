import { Fragment, memo, MouseEvent, useEffect, useMemo, useRef, useState } from 'react';
import { usePopupWindow } from './popupWindow';
import { Blocked, PopupPortal } from './popupParts';
import { RUNS_WINDOW } from '../contract';
import { api, Json } from '../api';
import { tasksShared } from '../shared';
import { bytes, clock, durationTenths as span, folderName, plural, RUN_STATE_CLASS as STATE_CSS, runTask as taskOf, sig, stamp, stopWords } from '../format';
import { CONTINUE_STATES, isLive } from '../runState';
import { FolderMoveBar, Folders, useFolders } from './Folders';
import { TableHead, useTableView } from './TableView';
import { childrenOf, historyOf, startedFrom } from '../lineage';
import { OPEN_RUNS, openTasksAt, RunsAt } from '../openAt';
import { MODE_NAME, runDesign, runMode } from './rlModelText';
import { pairs, variables } from '../units';

/** An experiment's folder by its name (branch record SIF-4): the folder's hash ("__ae6e1ae24977") only in the tooltip, and a
 *  line may break after "-" or "_" - the column wrapped "r5-dffr-powermid-bodata-s2_ae6e1a / e24977" between any letters. */
const experimentName = (folder?: string | null) => String(folder ?? '').replace(/__[0-9a-f]{8,}$/, '');
/** A run's saved state in the saved models' words (branch record SIF-20: "full_state" in the Details). */
const SAVED_STATE: Record<string, string> = { full_state: 'full state', weights_only: 'weights only' };
/** Where a name may break: after "-", "_" or "." - and at a space - never inside a word (branch record SIF-75). The "." is a
 *  baseline's or a calibration's task ("agentic_fc_pub.calibration"): whole, "pub.calibration" made the Task column 99 px and
 *  the table, with the user's 549 runs, 1259 px in its 1234. */
const breakAt = (text: string) => text.split(/(?<=[-_.])/).map((part, i) => <Fragment key={i}>{i > 0 && <wbr />}{part}</Fragment>);
/** A date never breaks at its hyphens (branch record SIF-27): in a narrow column "2026-10-20 13:09:11" goes date over time, not "2026-10-" over "20". */
const keepDates = (text: string) => text.split(/(\d{4}-\d\d-\d\d)/).map((part, i) => <Fragment key={i}>{i % 2 ? <span className="run-date">{part}</span> : part}</Fragment>);

/** Which run the bottom tabs show (user request 2026-09-21): ONE button at the right end of the bottom tab strip, where
 *  the drop-down list of runs used to be. It only reads "Runs..."; the run that is shown is named as plain text to its
 *  LEFT. Pressing it opens the run window - a browser window of its own, drawn through a portal like the connection
 *  window - with every run under the output folder as a table: when it started and finished, how long it worked, and
 *  what it was and came to. A double click on a row shows that run; "Details" adds the rest; "Clear" shows no run.
 *  Choosing a task (the Tasks window) shows that task's newest run, or none (App.tsx, record 7.212).
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
 *  filtered to one task's runs (openAt.ts): following a link changes no draft, no shown run and no running job.
 *
 *  Actions (record 7.267, plan "Load run" and "Existing runs: continued in place"), in a run's Details: **Load run** - also a
 *  double click - brings its task into the editors and its model into the next run, and shows its results; **Show results**
 *  only shows them in the bottom tabs; **Continue...** goes on with the run in its own folder (Run status's form; for a paused,
 *  stopped, interrupted or completed run with a full save point, branch record SIF-90); **New run
 *  like this** makes the next run repeat it. Load run and New run like this need the run's task registered now; the
 *  reason stands beside them when it is not, and a double click then shows the results. The draft changes are App.tsx's.
 *
 *  The window closes once a run is chosen (user request 2026-10-09: "after selecting one target task, model or run, close
 *  the pop up window"): after Show results and Continue..., and after Load run and New run like this once they went through -
 *  Cancel at the edits question or a model that cannot be read leaves it open, with the reason on the page and here (branch
 *  record SIF-84). Clear, Details, the folders and the links inside the window keep it open. */

// `state`: what the page's own status poll says now - the list row keeps the state of its last read ("starting").
// The run shown, left of Runs...: its start, task, Mode (as the RL model window names it), seed and state, set apart by "·"
// as the page's other lines are (branch record SIF-6: "2026-10-16 16:32:51 | mscr_vco_lin_c | scratch seed0 | completed").
const label = (r: Json, state?: string | null) => `${stamp(r.created_utc) ?? 'unknown time'} · ${taskOf(r)} · ${runMode(r)}, seed ${r.seed} · ${state ?? r.state ?? 'not started'}${r.mock ? ' · MOCK' : ''}`;
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

type Column = { key: string; title: string; help: string; numeric?: boolean; value?: (r: Json, byDir: Map<string, Json>) => string | number | null };
const COLUMNS: Column[] = [
  { key: 'started', title: 'Started', help: 'When the run was created (local time of this computer).', value: r => r.created_utc ?? null },
  { key: 'finished', title: 'Finished', help: 'When the run came to rest: completed, stopped, failed or paused. A run that is working has no finish time yet.', value: r => (isLive(r) ? null : r.ended_utc ?? r.last_seen_utc ?? null) },
  { key: 'duration', numeric: true, title: 'Duration', help: 'How long the run was actually working. The time it sat paused is not counted; "Details" shows it.', value: r => r.active_seconds ?? null },
  { key: 'state', title: 'State', help: 'How the run stands, and under it why it stopped.', value: r => r.state ?? '' },
  { key: 'task', title: 'Task', help: 'The task (circuit and its targets) the run optimizes.', value: r => taskOf(r) },
  { key: 'mode', title: 'Mode', help: 'New model = from random weights; Fine-tune and Evaluate only = from a saved model; Baseline, Calibration and Offline training by their names. Under it, the design of the network the run trains or evaluates (GraphGPS, RGCN, ...).', value: r => `${runMode(r)} ${runDesign(r)}` },
  { key: 'from', title: 'Started from', help: 'Where the run\'s model came from: "template GT" = a new model made from an encoder\'s template; "ota7t (2) @ 420" = the saved model it loaded and the save point (its evaluations), a link to that run; "offline: 22 runs" = a model trained offline on recorded runs; "-" = a baseline or a calibration, which loads none.',
    value: (r, byDir) => startedFrom(r, byDir).text },
  { key: 'model', title: 'Saved model', help: 'The name of the RL model this run saves; every model under the output folder has one of its own, so a name already given gets a number. Empty for a run that saves none (a baseline, LLM only).', value: r => r.model_label ?? null },
  { key: 'seed', numeric: true, title: 'Seed', help: 'The random seed of the run.', value: r => r.seed ?? null },
  { key: 'evaluations', numeric: true, title: 'Evaluations', help: 'Candidate designs simulated so far, of the budget the run was given.', value: r => r.evaluations ?? null },
  { key: 'feasible', numeric: true, title: 'First feasible', help: 'How many evaluations had been spent when the first design met every target. "none" = no design has met them.', value: r => r.first_feasible_eval_count ?? null },
  { key: 'experiment', title: 'Experiment', help: 'The experiment folder the run belongs to.', value: r => r.experiment ?? '' },
  { key: 'data', title: 'Data', help: 'MOCK = the built-in synthetic backend, not a circuit result. real = Virtuoso / Spectre simulations.', value: r => (r.mock ? 'mock' : 'real') },
  { key: 'resume', title: 'Can continue', help: 'Whether the saved state allows this run to be continued: yes (full state), model only (usable for Fine-tune and Evaluate only - also a full save point written by an older version of the optimizer code, which only that version can continue), no - also when the run folder no longer holds its save point (a copy made without them, or deleted ones).', value: r => r.resumability ?? '' },
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
  // A run's Mode in words here too, as its Mode column (branch record SIF-44: "· scratch ·", "2026-10-20 13:09:11 fine_tune").
  const stepText = (s: Json) => `${s?.task_key ?? (s ? taskOf(s) : '?')} · ${s ? runMode(s) || '?' : '?'} · ${s?.evaluations != null
    ? `${s.evaluations} evaluation${s.evaluations === 1 ? '' : 's'}` : 'evaluations unknown'}${s?.model_label ? ` · ${s.model_label}` : ''}`;
  return (<table className="grid small run-relations"><tbody>
    <tr><td>Task</td><td>{row.task_key ? <button className="item-link" onClick={() => openTasksAt({ task_key: row.task_key, from })}
        title="Open the Tasks window at this task.">{task && typeof task.name === 'string' && task.name !== row.task_key.replace(/^[^:]+:/, '') ? `${task.name} (${row.task_key})` : row.task_key}</button> : taskOf(row)}
      {row.task_definition_hash && <span className="hint"> · definition {String(row.task_definition_hash).slice(0, 12)}</span>}
      {task?.revision != null && <span className="hint"> · revision {task.revision} now</span>}
      {savedSince && <span className="warn"> · saved again since this run ({stamp(task.saved_utc)})</span>}
      {row.task_key && tasks.size > 0 && !task && <span className="hint"> · no longer registered</span>}</td></tr>
    <tr><td>Started from</td><td>{row.run_kind === 'offline_pretraining'
        ? <>trained offline on {row.pretraining_sources ?? sources.length} recorded runs
            {sources.length > 0 && <details className="more"><summary>the recorded runs</summary><ul className="steps-list">{sources.map((s: Json) =>
              <li key={s.run_dir}>{runLink(s.run_dir, `${s.task ?? '?'} · ${s.evaluations ?? '?'} evaluations · ${folderName(s.run_dir)}`)}</li>)}</ul></details>}</>
        : origin.parent ? <>{runLink(origin.parent, origin.text)}{row.parent?.checkpoint_id
            && <span className="hint">{` (${row.parent.relation === 'frozen' ? 'evaluated' : 'fine-tuned'} from its save point ${row.parent.checkpoint_id})`}</span>}</>
        : origin.text === '-' ? <span className="hint">no model: {row.run_kind === 'calibration' ? 'a calibration' : 'a baseline simulation'} loads none</span>
        : <>{origin.text} <span className="hint">(a new model)</span></>}</td></tr>
    <tr><td>Saved model</td><td>{row.model_label ? <>{row.model_label}{info && <span className="hint"> · latest save point {info.save_point ?? 'none'}</span>}</>
      : <span className="hint">none</span>}</td></tr>
    <tr><td>Runs that started from its model</td><td>{children.length ? children.map((c, i) => <Fragment key={c.run_dir}>{i > 0 && ', '}
      {runLink(c.run_dir, `${stamp(c.created_utc) ?? folderName(c.run_dir)} ${runMode(c)}${c.model_label ? ` (${c.model_label})` : ''}`)}</Fragment>)
      : <span className="hint">none under this output folder</span>}</td></tr>
    <tr><td>History</td><td><details className="more run-history"><summary>{behind ? `${behind} model${behind > 1 ? 's' : ''} behind this run, oldest first` : 'no saved model behind this run'}</summary>
      <ol className="steps-list"><li className={history.root.missing ? 'warn' : 'hint'}>{history.root.text}</li>
        {history.steps.map(s => <li key={s.run_dir}>{s.run_dir === row.run_dir ? <b>this run</b> : runLink(s.run_dir, stepText(s.row))}
          {s.checkpoint_id && <span className="hint"> - loaded the one above at its save point {s.checkpoint_id}</span>}</li>)}</ol></details></td></tr>
  </tbody></table>);
}

/** Why Load run and New run like this are not offered for a run (record 7.267), or null. `tasks`: the registered tasks as
 *  read when the window opened (empty until then: the load itself says so if the task is gone). */
export function loadBlocked(row: Json, tasks: Map<string, Json>): string | null {
  if (!row.task_key) return 'Not offered: the run names no registered task (a Virtuoso cell never saved as a task, or a run older than task keys). Show results still works, and its model can be used from the RL model window.';
  if (tasks.size > 0 && !tasks.has(row.task_key)) return `Not offered: its task ${row.task_key} is no longer registered. Show results still works, and its model can be used from the RL model window.`;
  return null;
}

/** Everything else about one run. `row` is its line of the list; `info` is /api/runs/status, read when the details open. */
function RunDetails({ row, info, error, onCopy, copied, relations, actions }: { row: Json; info: Json; error?: string; onCopy: (text: string) => void; copied: boolean;
  relations: JSX.Element; actions?: JSX.Element | null }) {
  const b = info?.budget, best = info?.best_design, first = info?.first_feasible, summary = info?.summary, source = info?.manifest?.source_model;
  const facts: [string, string | null | undefined][] = [
    ['Run id', row.run_id], ['Registered task', row.task_key], ['Task id', row.task_id], ['Experiment', row.experiment],
    ['Created', stamp(row.created_utc)], ['Worker began', stamp(row.started_utc)], ['Came to rest', stamp(row.ended_utc)], ['Last sign of life', row.ended_utc ? null : stamp(row.last_seen_utc)],
    ['Worked for', span(row.active_seconds)], ['Paused between segments', row.paused_seconds ? span(row.paused_seconds) : null],
    ['Summed simulator job time', summary?.time?.sum_job_runtime_seconds != null ? `${span(summary.time.sum_job_runtime_seconds)} (parallel jobs added up: not elapsed time)` : null],
    ['Stop reason', row.stop_reason ? `${stopWords(row.stop_reason)} (${row.stop_reason})` : null], ['Error', row.error],   // words, the key beside them (SIF-16)
    // "used", as Run status, the Continue... form and the Abort question count the budget (SIF-76: "charged")
    ['Budget', b ? `${b.charged} used / ${b.max_evaluations} (completed ${b.completed}, failed ${b.failed}, in flight ${b.in_flight}, remaining ${b.remaining})` : null],
    ['Spectre launches', b ? `${b.launches}${b.max_launches ? ' / ' + b.max_launches : ''} (retries ${b.retries}, cache hits ${b.cache_hits})` : null],
    ['Learner updates', info ? String(info.learner_updates ?? 0) : null],
    ['First feasibility', info ? (first ? `at ${plural(first.first_feasible_eval_count, 'evaluation')} used (${first.completed_count} completed, ${plural(first.spectre_launches, 'launch', 'launches')})` : 'not reached') : null],   // one as one (SIF-76 review)
    ['Best design', info ? (best ? `${best.feasible ? 'feasible' : 'infeasible'} · ${pairs(best.metrics, best.metric_units)} · violation ${typeof best.violation === 'number' ? sig(best.violation) : '-'}` : 'none') : null],   // not shouted (SIF-19); three digits (SIF-44)
    ['Best design variables', best?.variables ? variables(best.variables) : null],
    ['Model loaded at the start', info ? (source?.run_id ? `run ${String(source.run_id).slice(0, 12)} / ${source.checkpoint_id}` : 'none (random weights)') : null],
    ['Last save point', info ? stamp(info.last_checkpoint_utc) ?? 'none' : null],   // as Run status names it (SIF-70: "Last model save")
    // a save point the summary names but the run folder no longer holds (a copy made without them, deleted ones): said (7.215)
    ['Saved state', summary?.output ? (info?.save_point === null && summary.output.resumability !== 'none'
      ? `none: the run's summary names its save point ${summary.output.latest_checkpoint ?? ''} as ${SAVED_STATE[summary.output.resumability] ?? summary.output.resumability}, but the run folder no longer holds it (a copy made without its save points, or they were deleted); nothing to continue from`
      // a full save point of an older optimizer source: only that source can continue it (record 7.221); the Modes as
      // their buttons name them (it said "fine-tune and frozen"; branch record SIF-53)
      : info?.save_point_code === 'older' && summary.output.resumability === 'full_state'
      ? `model only: the latest save ${summary.output.latest_checkpoint ?? ''} is a full save point written by an older version of the optimizer code - only that version can continue it; Fine-tune and Evaluate only still load its model`
      : `${SAVED_STATE[summary.output.resumability] ?? summary.output.resumability} (${summary.output.completeness} output, latest save ${summary.output.latest_checkpoint ?? 'none'})`) : null],
    ['Concurrent Spectre jobs', info?.concurrency ? `${info.concurrency}` : null],   // Run configuration's name (SIF-54: "Parallel simulations")
    ['Connection', info?.connection_profile_id ?? (info ? 'none (not needed)' : null)],
    ['Data written', info?.bytes_written != null ? bytes(info.bytes_written) : null],
  ];
  return (<div className="run-details">
    {actions}
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
          <td>{s.end_state ?? '-'}</td><td title={s.stop_reason ?? undefined}>{s.stop_reason ? stopWords(s.stop_reason) : '-'}</td><td className="numeric">{span(s.active_seconds) ?? '-'}</td></tr>)}</tbody></table></>}
  </div>);
}

/** What Load run and New run like this answer (branch record SIF-84): whether they went through, and when not and not
 *  overtaken by a newer choice, the page message's sentence saying why. */
export type RunChoice = { loaded: boolean; why?: string };

/** `headerDir`: the header's run while it works or is paused (App.tsx); when the tabs show another, the line says so.
 *  `onLoad` and `onNewLike` get this window: it asks the edits question (branch record SIF-84). */
function RunListButtonBody({ runs, runsError, runDir, shownState, onChoose, onRefresh, onLoad, onNewLike, onContinue, headerDir = null }: { runs: Json[]; runsError: string | null; runDir: string | null;
  shownState: string | null; onChoose: (runDir: string | null) => void; onRefresh: (fresh?: boolean) => Promise<Json[]>;
  onLoad?: (row: Json, owner?: Window | null) => Promise<RunChoice> | void; onNewLike?: (row: Json, owner?: Window | null) => Promise<RunChoice> | void;
  onContinue?: (row: Json) => void; headerDir?: string | null }) {
  // While `popup` is set, the run window is open (one pop-up window for the whole page: `popupWindow.ts`).
  const { popup, root, blocked, open: openPopup } = usePopupWindow('gator-runs',
    { title: RUNS_WINDOW, features: 'popup,width=1500,height=860', rootId: 'runs-root' });
  const [loading, setLoading] = useState(false);
  const [readAt, setReadAt] = useState<string | null>(null);
  const table = useTableView('started', true);
  const { filter, setFilter, selected, setSelected } = table;
  const [open, setOpen] = useState<string | null>(null);        // the run whose details are shown
  const [info, setInfo] = useState<{ dir: string; value?: Json; error?: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const folders = useFolders('runs');
  const [onlyTask, setOnlyTask] = useState<string | null>(null);   // only one task's runs: a link from the Tasks window (7.264)
  const [tasks, setTasks] = useState<Map<string, Json>>(new Map());
  const [focus, setFocus] = useState<string | null>(null);         // a run to scroll to once it is drawn
  const byDir = useMemo(() => new Map(runs.map(r => [r.run_dir, r])), [runs]);
  const readTasks = (fresh = false) => tasksShared(fresh).then(read => setTasks(new Map((read.tasks ?? []).map((x: Json) => [x.task_key, x]))), () => undefined);
  const chooseFolder = (id: string) => { folders.setFolder(id); setSelected([]); setOpen(null); };

  const readDetails = (dir: string) => { setInfo({ dir }); api.status(dir).then(value => setInfo(i => (i?.dir === dir ? { dir, value } : i)), e => setInfo(i => (i?.dir === dir ? { dir, error: e.message } : i))); };
  // `fresh`: the Refresh list press reads every run folder anew (record 7.274); the window's opening uses the backend's cache.
  const lastRead = useRef(0);
  const refresh = (fresh = false) => { setLoading(true); setSelected([]); setRefused(null); void folders.refresh(); void readTasks(fresh);
    onRefresh(fresh).finally(() => { setLoading(false); lastRead.current = Date.now(); setReadAt(clock()); }); if (open) readDetails(open); };
  /** Show one run in this window: every folder, no filter, its Details open, scrolled to. */
  const focusRun = (dir: string) => {
    folders.setFolder('all'); setFilter(''); setSelected([]);
    setOnlyTask(task => (task && byDir.get(dir)?.task_key !== task ? null : task));
    setOpen(dir); readDetails(dir); setFocus(dir);
  };
  // Whoever had the list read - this window, or the page when a run was started - the window says when that was.
  useEffect(() => setReadAt(clock()), [runs]);
  // A Load run or New run like this that did not go through, and why (branch record SIF-84): the edits question is asked in
  // this window now, and the page's message line stands behind it. Beside the run's actions while its Details are open,
  // else in the count line (a double click); the next press, a Details toggle, Refresh list or closing the window lets it go.
  const [refused, setRefused] = useState<{ dir: string; why: string } | null>(null);
  useEffect(() => { if (!popup) setRefused(null); }, [popup]);
  const toggle = (dir: string) => { setRefused(null); if (open === dir) { setOpen(null); return; } setOpen(dir); readDetails(dir); };
  // A run chosen closes the window (user request 2026-10-09): at once, or once Load run / New run like this went through.
  const chosen = (done?: Promise<RunChoice> | void, row?: Json) => {
    const shown = popup;
    setRefused(null);
    void Promise.resolve(done).then(r => {
      if (!shown || shown.closed) return;
      if (r?.loaded !== false) shown.close(); else if (r.why && row) setRefused({ dir: row.run_dir, why: r.why });
    });
  };
  // A double click on a run's row loads the run (record 7.267, plan "Load run"; it only showed the run until then, user
  // request 2026-09-21: no "Show" column) - or shows it, where Load run is not offered. Not when it lands on the row's
  // "Details" button: that only opens and closes the details. The word the double click selected is let go.
  const showRun = (e: MouseEvent<HTMLTableRowElement>, row: Json) => {
    if ((e.target as HTMLElement).closest('button, input, select, label')) return;
    (popup ?? window).getSelection()?.removeAllRanges();
    if (onLoad && !loadBlocked(row, tasks)) chosen(onLoad(row, popup), row); else { onChoose(row.run_dir); chosen(); }
  };
  const actions = (r: Json) => {
    if (!onLoad) return null;
    const why = loadBlocked(r, tasks);
    // Continue... only where Run status can go on (branch record SIF-90): a full save point and a state it continues from. It
    // was offered for any run at rest that kept a save point, failed, cancelled and model-only ones too: the press closed this
    // window on a greyed-out budget form. Such a run says why beside the actions, and where its model can still go.
    const atRest = !isLive(r) && !!onContinue, kept = r.resumability != null && r.resumability !== 'none';
    const continuable = atRest && r.resumability === 'full_state' && CONTINUE_STATES.includes(r.state);
    const notContinued = !atRest || !kept || continuable ? null : r.state === 'failed' ? 'a failed run cannot be continued'
      : r.state === 'cancelled' ? 'a cancelled run cannot be continued' : r.resumability === 'weights_only' ? 'its save point is model only' : null;
    return <div className="row run-actions">
      <button className="run-load" disabled={!!why} onClick={() => chosen(onLoad(r, popup), r)} title={why ?? 'Load run (also a double click on the run): its task comes into the editors - edits are asked about first -, its model becomes the next run\'s model, pinned, and the bottom tabs show its results. One Undo step takes the task and the model back. Nothing starts.'}>Load run</button>
      <button className="run-show" onClick={() => { onChoose(r.run_dir); chosen(); }} title="Show results: the bottom tabs show this run (Run status, Logs, Data tables...). Nothing else changes.">Show results</button>
      {continuable && <button className="run-continue" onClick={() => { onContinue!(r); chosen(); }} title="Continue...: the run goes on in its own folder, from its newest save point, with its own settings - Run status shows it, with the budget form.">Continue...</button>}
      {onNewLike && <button className="run-like" disabled={!!why} onClick={() => chosen(onNewLike(r, popup), r)} title={why ?? 'New run like this: the next run repeats this one - its task (edits are asked about first), Mode, the model it started from, network, training values, reward, conditions, budget, seed and limits. One Undo step. Nothing starts.'}>New run like this</button>}
      {why && <span className="hint run-load-why">{why}</span>}
      {notContinued && <span className="hint continue-not">Continue... is not offered: {notContinued}.{why ? '' : ` Load run brings its model into the next run (${MODE_NAME.fine_tune} or ${MODE_NAME.frozen}).`}</span>}
      {refused && refused.dir === r.run_dir && <span className="hint run-refused" role="status">{refused.why}</span>}
    </div>;
  };

  // Pressing Runs... is the request to see the current list. A link from another window (`link`) only opens the window at
  // an item: it reads the list again when the window was closed or its list is older than a minute (record 7.275).
  const openWindow = (from?: Window | null, link = false) => {
    if (!link || !popup || Date.now() - lastRead.current > 60_000) refresh();
    openPopup(from);
  };
  // Another window's link (openAt.ts): this window opens AT a run, or with one task's runs only.
  const latest = useRef({ openWindow, focusRun });
  latest.current = { openWindow, focusRun };
  useEffect(() => {
    const show = (event: Event) => {
      const at = (event as CustomEvent<RunsAt>).detail ?? {};
      latest.current.openWindow(at.from, true);
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
  const elsewhere = headerDir && headerDir !== runDir ? headerDir : null;          // the header's run, when these tabs show another
  const text =(r: Json) => [stamp(r.created_utc), stamp(r.ended_utc), taskOf(r), r.task_key, r.task_id, r.mode, runMode(r), runDesign(r), r.model_label, `seed${r.seed}`, r.state, r.stop_reason, stopWords(r.stop_reason), r.experiment, r.mock ? 'mock' : 'real', folderName(r.run_dir),
    folders.data.folders[folders.of(r.run_dir)]].join(' ').toLowerCase();
  const column = COLUMNS.find(c => c.key === table.sort.key) ?? COLUMNS[0];
  // Only while the window is open: the page redraws on every status poll, and a closed window needs no sorted list.
  const shown = !popup ? [] : table.arrange(runs, r => folders.holds(r.run_dir) && (!onlyTask || r.task_key === onlyTask), text, r => column.value!(r, byDir));
  const timed = runs.some(r => 'active_seconds' in r);     // an older workbench server lists runs without their times

  const view = popup && root && (
    <div className="run-window">
      <h2>Runs</h2>
      <div className="row">
        <button onClick={() => refresh(true)} disabled={loading || folders.busy} title="Refresh list: every run folder is read again from the disk.">Refresh list</button>
        <button onClick={() => onChoose(null)} disabled={!runDir} title="The bottom tabs of the workbench show no run. Nothing is stopped or deleted.">Clear</button>
        <input className="run-filter" placeholder="Filter: task, mode, state, mock / real, date ..." value={filter} onChange={e => { setFilter(e.target.value); setSelected([]); }} />
        {/* a double click that did not go through says why here, where the count stood (branch record SIF-84) */}
        {refused && open !== refused.dir ? <span className="hint run-count run-refused" role="status">{refused.why}</span>
          : <span className="hint run-count">{loading ? 'Reading the runs...' : runsError ? 'The list could not be read.'
          : `${runs.length} run${runs.length === 1 ? '' : 's'} under the output folder${readAt ? `, read at ${readAt}` : ''}. Nothing here updates by itself.`}</span>}
      </div>
      {runsError && !loading && <p className="error run-list-error">The run list could not be read: {runsError}</p>}
      {folders.error && <p className="error" role="alert">{folders.error} Press Refresh list to retry.</p>}
      {onLoad ? <p className="hint"><b>Double click</b> a run to load it: its task comes into the editors, its model becomes the next run's model, and the bottom tabs of the workbench show its results (one Undo step takes the task and the model back; nothing starts). A run's <b>Details</b> also offer <b>Show results</b> alone, <b>Continue...</b> and <b>New run like this</b>. The run that is shown is marked; <b>Clear</b> shows no run. Choosing a task under <b>Task</b> shows its newest run, or none if it has none. The window closes once a run is loaded, shown, continued or repeated - it stays open, saying why, when that does not go through (Cancel at the edits question, a model that cannot be read), and for <b>Clear</b> and <b>Details</b>.</p>
        : <p className="hint"><b>Double click</b> a run to show it in the bottom tabs of the workbench (Run status, Logs, Data tables, Output files); the run that is shown is marked, and the window then closes. <b>Clear</b> shows no run. Choosing a task under <b>Task</b> shows its newest run, or none if it has none.</p>}
      <details className="more"><summary>What the columns mean</summary>
        <ul className="steps-list">{COLUMNS.map(c => <li key={c.key}><b>{c.title}</b>: {c.help}</li>)}
          <li>All times are the local time of this computer. Press a column title to sort by it. "Details" shows everything else the run recorded.</li></ul></details>
      {runs.length > 0 && !timed && <p className="warn">The workbench server that is running is older than this page and does not report when a run finished or how long it took.
        Restart it (Ctrl+C in its terminal, then start `serve` again) and press "Refresh list".</p>}
      {runs.length === 0 && !loading && !runsError && <p className="hint run-empty">No run yet under this output folder. A run appears here as soon as it has been started.</p>}
      <div className="task-browser">
      <Folders state={folders} keys={runs.map(r => r.run_dir)} popup={popup} onSelect={chooseFolder} />
      <div className="task-folder-content">
      <FolderMoveBar state={folders} shown={shown.length} selected={selected.length} onMove={id => void table.move(folders, id)} />
      {onlyTask && <p className="hint run-only-task">Only the runs of <code>{onlyTask}</code>{' '}
        <button className="item-link" onClick={() => setOnlyTask(null)}>Show every run</button></p>}
      {runs.length > 0 && <div className="scroll"><table className="grid run-table">
        <TableHead view={table} columns={COLUMNS} shown={shown} id={r => r.run_dir} what="runs" disabled={folders.busy || !folders.ready} />
        <tbody>{shown.map(r => { const active = r.run_dir === runDir, end = finished(r), origin = startedFrom(r, byDir); return (<Fragment key={r.run_dir}>
          <tr className={active ? 'current' : ''} aria-current={active ? 'true' : undefined} title={r.run_dir} onDoubleClick={e => showRun(e, r)}>
            <td className="task-select"><input type="checkbox" aria-label={`Select ${folderName(r.run_dir)}`} checked={selected.includes(r.run_dir)}
              disabled={folders.busy || !folders.ready} onChange={e => table.select(r.run_dir, e.target.checked)} /></td>
            <td className="wrap-words">{keepDates(stamp(r.created_utc) ?? '-')}{folders.folder === 'all' && folders.data.folders[folders.of(r.run_dir)]
              && <div className="hint task-folder-label">{folders.data.folders[folders.of(r.run_dir)]}</div>}</td>
            <td className={`wrap-words${end.css ? ` ${end.css}` : ''}`} title={end.title}>{keepDates(end.text)}</td>
            {/* "so far" may go under the time (roadster.css, branch record SIF-64): on one line it made the table wider than its window */}
            <td className="numeric" title={r.paused_seconds ? `Working time. It also sat paused for ${span(r.paused_seconds)}.` : undefined}>{span(r.active_seconds) ?? '-'}{isLive(r) && r.active_seconds != null && <span className="run-so-far"> so far</span>}</td>
            <td className="wrap-words"><span className={`badge state-${STATE_CSS[r.state] ?? 'unknown'}`}>{r.state ?? 'not started'}</span>{r.stop_reason && <div className="hint" title={r.stop_reason}>{stopWords(r.stop_reason)}</div>}</td>
            {/* Branch record SIF-75: a task and a saved model break only at a space or after "-", "_" or ".", never inside a word
                ("graphgps" over "_ldo1", "graphgps_ld" over "o1 (31)"), and so does the model a run started from where the column
                holds the word; the link takes three lines at most (roadster.css), the whole name first in its tooltip - an offline
                model's name took six lines, its row 120 px. That cell keeps "wrap": a run that is not under this output folder is
                named by its folder, whose 12-character hash would otherwise widen the column and the table past its window. */}
            <td className="wrap-words" title={r.task_id}>{breakAt(taskOf(r))}</td><td className="wrap-words">{runMode(r)}{runDesign(r) && <span className="hint run-design">{runDesign(r)}</span>}</td>
            <td className="wrap run-from">{origin.parent ? <button className="item-link" onClick={() => focusRun(origin.parent!)} title={`${origin.text}\n${origin.parent}\nShow the run it started from.`}>
              <span className="run-from-name">{breakAt(origin.text)}</span></button> : origin.text}
              {origin.missing && <span className="hint" title="That run is not under this output folder."> (gone)</span>}</td>
            <td className="wrap-words">{breakAt(r.model_label ?? '-')}</td><td className="numeric">{r.seed}</td>
            <td className="numeric">{r.evaluations ?? '-'}{r.max_evaluations != null && ` / ${r.max_evaluations}`}</td>
            <td className="numeric">{r.first_feasible_eval_count != null ? `at ${r.first_feasible_eval_count}` : r.evaluations != null ? 'none' : '-'}</td>
            <td className="wrap-words run-experiment" title={r.experiment}>{breakAt(experimentName(r.experiment))}</td>
            <td>{r.mock ? <span className="badge model-tag mock-tag">MOCK</span> : 'real'}</td>
            <td>{RESUME[r.resumability] ?? '-'}</td>
            <td><button className="notes-link" aria-expanded={open === r.run_dir} onClick={() => toggle(r.run_dir)}>{open === r.run_dir ? 'Hide details' : 'Details'}</button></td>
          </tr>
          {open === r.run_dir && <tr className="run-details-row"><td colSpan={COLUMNS.length + 2}>
            <RunDetails row={r} info={info?.dir === r.run_dir ? info?.value : null} error={info?.dir === r.run_dir ? info?.error : undefined} onCopy={copyPath} copied={copied}
              actions={actions(r)} relations={<Relationships row={r} info={info?.dir === r.run_dir ? info?.value : null} runs={runs} byDir={byDir} tasks={tasks} from={popup} onFocus={focusRun} />} /></td></tr>}
        </Fragment>); })}</tbody></table></div>}
      {runs.length > 0 && shown.length === 0 && <p className="hint task-folder-empty">{filter ? 'No run matches the filter in this folder.' : 'This folder is empty. Select runs in All runs, then use Move to…'}</p>}
      </div></div>
    </div>
  );

  return (<>
    {blocked && <Blocked as="span" className="error run-list-blocked" />}
    {/* The run that is shown is said as plain text to the LEFT of the button; the button itself only reads "Runs..." (user request 2026-09-21). */}
    {/* Branch record SIF-72: while the header's run works or is paused and these tabs show another, the line says "Shown:" and
        offers the header's run - it showed "... mscr_vco_lin_c · New model, seed 0 · completed" under a header running 270 of 800. */}
    <span className="run-list-current" title={runDir ?? undefined}>{elsewhere && runDir ? 'Shown: ' : ''}{current ? label(current, shownState) : runDir ? folderName(runDir) : 'No run selected'}</span>
    {elsewhere && <span className="run-list-header"><button className="item-link" onClick={() => onChoose(elsewhere)}
      title={`The header holds another run, the one its buttons act on: ${elsewhere}\nPress to show it in these tabs.`}>Show the header's run</button></span>}
    <button className={`run-list-button${popup ? ' open' : ''}`} onClick={() => openWindow()}
      title={popup ? 'The run window is open: press to bring it to the front and read the list again.' : 'Opens the run window: every run with its start and finish time, its duration and its results. Choose there which run these tabs show; the window then closes.'}>Runs...</button>
    <PopupPortal popup={popup} root={root}>{view}</PopupPortal>
  </>);
}

/** Memoised (record 7.279): it gets the shown run's state, not the whole status, and App.tsx hands it callbacks that stay
 *  the same functions - so a status update no longer draws the open window's table (124 runs: 3,500 parts) again. */
export const RunListButton = memo(RunListButtonBody);
