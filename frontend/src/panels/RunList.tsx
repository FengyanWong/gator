import { Fragment, MouseEvent, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { BLOCKED, usePopupWindow } from './popupWindow';
import { api, bytes, Json, short } from '../api';
import { LIVE_STATES } from './RunControl';

/** Which run the bottom tabs show (user request 2026-09-21): ONE button at the right end of the bottom tab strip, where
 *  the drop-down list of runs used to be. It only reads "Runs..."; the run that is shown is named as plain text to its
 *  LEFT. Pressing it opens the run window - a browser window of its own, drawn through a portal like the connection
 *  window - with every run under the output folder as a table: when it started and finished, how long it worked, and
 *  what it was and came to. A double click on a row shows that run; "Details" adds the rest; "Clear" shows no run.
 *
 *  Nothing here updates on a timer: the list is read when the button is pressed and by "Refresh list", a run's details
 *  when they are opened. So a run that is working shows the state and duration AS OF the read time, which is printed. */

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
const label = (r: Json) => `${stamp(r.created_utc) ?? 'unknown time'} | ${taskOf(r)} | ${r.mode} seed${r.seed} | ${r.state ?? 'not started'}${r.mock ? ' [MOCK]' : ''}`;
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

type Column = { key: string; title: string; help: string; value?: (r: Json) => string | number | null; numeric?: boolean };
const COLUMNS: Column[] = [
  { key: 'started', title: 'Started', help: 'When the run was created (local time of this computer).', value: r => r.created_utc ?? null },
  { key: 'finished', title: 'Finished', help: 'When the run came to rest: completed, stopped, failed or paused. A run that is working has no finish time yet.', value: r => (isLive(r) ? null : r.ended_utc ?? r.last_seen_utc ?? null) },
  { key: 'duration', title: 'Duration', help: 'How long the run was actually working. The time it sat paused is not counted; "Details" shows it.', value: r => r.active_seconds ?? null, numeric: true },
  { key: 'state', title: 'State', help: 'How the run stands, and under it why it stopped.', value: r => r.state ?? '' },
  { key: 'task', title: 'Task', help: 'The task (circuit and its targets) the run optimizes.', value: r => taskOf(r) },
  { key: 'mode', title: 'Mode', help: 'scratch = from random weights; fine_tune / frozen / resume = from a saved model.', value: r => r.mode ?? '' },
  { key: 'seed', title: 'Seed', help: 'The random seed of the run.', value: r => r.seed ?? null, numeric: true },
  { key: 'evaluations', title: 'Evaluations', help: 'Candidate designs simulated so far, of the budget the run was given.', value: r => r.evaluations ?? null, numeric: true },
  { key: 'feasible', title: 'First feasible', help: 'How many evaluations had been spent when the first design met every target. "none" = no design has met them.', value: r => r.first_feasible_eval_count ?? null, numeric: true },
  { key: 'experiment', title: 'Experiment', help: 'The experiment folder the run belongs to.', value: r => r.experiment ?? '' },
  { key: 'data', title: 'Data', help: 'MOCK = the built-in synthetic backend, not a circuit result. real = Virtuoso / Spectre simulations.', value: r => (r.mock ? 'mock' : 'real') },
  { key: 'resume', title: 'Can continue', help: 'Whether the saved state allows this run to be continued: yes (full state), model only (usable for fine_tune / frozen), no.', value: r => r.resumability ?? '' },
];

/** Everything else about one run. `row` is its line of the list; `info` is /api/runs/status, read when the details open. */
function RunDetails({ row, info, error, onCopy, copied }: { row: Json; info: Json; error?: string; onCopy: (text: string) => void; copied: boolean }) {
  const b = info?.budget, best = info?.best_design, first = info?.first_feasible, summary = info?.summary, source = info?.manifest?.source_model;
  const facts: [string, string | null | undefined][] = [
    ['Run id', row.run_id], ['Task id', row.task_id], ['Experiment', row.experiment],
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
    ['Saved state', summary?.output ? `${summary.output.resumability} (${summary.output.completeness} output, latest save ${summary.output.latest_checkpoint ?? 'none'})` : null],
    ['Parallel simulations', info?.concurrency ? `${info.concurrency} (threads per job ${info.threads_per_job})` : null],
    ['Connection', info?.connection_profile_id ?? (info ? 'none (not needed)' : null)],
    ['Data written', info?.bytes_written != null ? bytes(info.bytes_written) : null],
  ];
  return (<div className="run-details">
    {error && <p className="error">The details of this run could not be read: {error}</p>}
    {!info && !error && <p className="hint">Reading the run's details...</p>}
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

export function RunListButton({ runs, runDir, onChoose, onRefresh }: { runs: Json[]; runDir: string | null; onChoose: (runDir: string | null) => void; onRefresh: () => Promise<Json[]> }) {
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

  const readDetails = (dir: string) => { setInfo({ dir }); api.status(dir).then(value => setInfo(i => (i?.dir === dir ? { dir, value } : i)), e => setInfo(i => (i?.dir === dir ? { dir, error: e.message } : i))); };
  const refresh = () => { setLoading(true); onRefresh().finally(() => setLoading(false)); if (open) readDetails(open); };
  // Whoever had the list read - this window, or the page when a run was started - the window says when that was.
  useEffect(() => setReadAt(new Date().toLocaleTimeString([], { hour12: false })), [runs]);
  const toggle = (dir: string) => { if (open === dir) { setOpen(null); return; } setOpen(dir); readDetails(dir); };
  // A double click on a run's row shows that run in the bottom tabs (user request 2026-09-21: no "Show" column). Not when it
  // lands on the row's "Details" button: that only opens and closes the details. The word the double click selected is let go.
  const showRun = (e: MouseEvent<HTMLTableRowElement>, dir: string) => {
    if ((e.target as HTMLElement).closest('button')) return;
    (popup ?? window).getSelection()?.removeAllRanges();
    onChoose(dir);
  };

  const openWindow = () => {
    refresh();                                                   // pressing the button is the request to see the current list
    openPopup();
  };
  // The click happens in the run window, so ITS clipboard is the one a browser lets this gesture write to.
  const copyPath = (text: string) => (popup ?? window).navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }, () => undefined);

  const current: Json = runs.find(r => r.run_dir === runDir) ?? null;
  const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
  const text = (r: Json) => [stamp(r.created_utc), stamp(r.ended_utc), taskOf(r), r.task_id, r.mode, `seed${r.seed}`, r.state, r.stop_reason, r.experiment, r.mock ? 'mock' : 'real', folder(r.run_dir)].join(' ').toLowerCase();
  const column = COLUMNS.find(c => c.key === sort.key) ?? COLUMNS[0];
  // Empty cells stay at the bottom whichever way the column is sorted.
  const shown = runs.filter(r => words.every(w => text(r).includes(w))).sort((a, b) => {
    const x = column.value!(a), y = column.value!(b);
    if (x == null || x === '' || y == null || y === '') return (x == null || x === '' ? 1 : 0) - (y == null || y === '' ? 1 : 0);
    return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))) * (sort.down ? -1 : 1);
  });
  const timed = runs.some(r => 'active_seconds' in r);     // an older workbench server lists runs without their times

  const view = (
    <div className="run-window">
      <h2>Runs</h2>
      <div className="row">
        <button onClick={refresh} disabled={loading}>Refresh list</button>
        <button onClick={() => onChoose(null)} disabled={!runDir} title="The bottom tabs of the workbench show no run. Nothing is stopped or deleted.">Clear</button>
        <input className="run-filter" placeholder="Filter: task, mode, state, mock / real, date ..." value={filter} onChange={e => setFilter(e.target.value)} />
        <span className="hint run-count">{loading ? 'Reading the runs...' : `${runs.length} run${runs.length === 1 ? '' : 's'} under the output folder${readAt ? `, read at ${readAt}` : ''}. Nothing here updates by itself.`}</span>
      </div>
      <p className="hint"><b>Double click</b> a run to show it in the bottom tabs of the workbench (Run status, Logs, Data tables, Output files); the run that is shown is marked. <b>Clear</b> shows no run. This window stays open until you close it.</p>
      <details className="more"><summary>What the columns mean</summary>
        <ul className="steps-list">{COLUMNS.map(c => <li key={c.key}><b>{c.title}</b>: {c.help}</li>)}
          <li>All times are the local time of this computer. Press a column title to sort by it. "Details" shows everything else the run recorded.</li></ul></details>
      {runs.length > 0 && !timed && <p className="warn">The workbench server that is running is older than this page and does not report when a run finished or how long it took.
        Restart it (Ctrl+C in its terminal, then start `serve` again) and press "Refresh list".</p>}
      {runs.length === 0 && !loading && <p className="hint run-empty">No run yet under this output folder. A run appears here as soon as it has been started.</p>}
      {runs.length > 0 && <div className="scroll"><table className="grid run-table">
        <thead><tr>
          {COLUMNS.map(c => <th key={c.key} className="sortable" title={`${c.help} Press to sort.`} aria-sort={sort.key === c.key ? (sort.down ? 'descending' : 'ascending') : undefined}
            onClick={() => setSort(s => ({ key: c.key, down: s.key === c.key ? !s.down : true }))}>{c.title}{sort.key === c.key && <span className="sort-mark">{sort.down ? ' ▼' : ' ▲'}</span>}</th>)}
          <th className="plain"></th></tr></thead>
        <tbody>{shown.map(r => { const active = r.run_dir === runDir, end = finished(r); return (<Fragment key={r.run_dir}>
          <tr className={active ? 'current' : ''} aria-current={active ? 'true' : undefined} title={r.run_dir} onDoubleClick={e => showRun(e, r.run_dir)}>
            <td>{stamp(r.created_utc) ?? '-'}</td>
            <td className={end.css} title={end.title}>{end.text}</td>
            <td className="numeric" title={r.paused_seconds ? `Working time. It also sat paused for ${span(r.paused_seconds)}.` : undefined}>{span(r.active_seconds) ?? '-'}{isLive(r) && r.active_seconds != null && ' so far'}</td>
            <td><span className={`badge state-${STATE_CSS[r.state] ?? 'unknown'}`}>{r.state ?? 'not started'}</span>{r.stop_reason && <div className="hint">{r.stop_reason}</div>}</td>
            <td title={r.task_id}>{taskOf(r)}</td><td>{r.mode}</td><td className="numeric">{r.seed}</td>
            <td className="numeric">{r.evaluations ?? '-'}{r.max_evaluations != null && ` / ${r.max_evaluations}`}</td>
            <td className="numeric">{r.first_feasible_eval_count != null ? `at ${r.first_feasible_eval_count}` : r.evaluations != null ? 'none' : '-'}</td>
            <td>{r.experiment}</td>
            <td>{r.mock ? <span className="badge model-tag mock-tag">MOCK</span> : 'real'}</td>
            <td>{RESUME[r.resumability] ?? '-'}</td>
            <td><button className="notes-link" aria-expanded={open === r.run_dir} onClick={() => toggle(r.run_dir)}>{open === r.run_dir ? 'Hide details' : 'Details'}</button></td>
          </tr>
          {open === r.run_dir && <tr className="run-details-row"><td colSpan={COLUMNS.length + 1}>
            <RunDetails row={r} info={info?.dir === r.run_dir ? info?.value : null} error={info?.dir === r.run_dir ? info?.error : undefined} onCopy={copyPath} copied={copied} /></td></tr>}
        </Fragment>); })}</tbody></table></div>}
      {runs.length > 0 && shown.length === 0 && <p className="hint">No run matches the filter.</p>}
    </div>
  );

  return (<>
    {blocked && <span className="error run-list-blocked">{BLOCKED}</span>}
    {/* The run that is shown is said as plain text to the LEFT of the button; the button itself only reads "Runs..." (user request 2026-09-21). */}
    <span className="run-list-current" title={runDir ?? undefined}>{current ? label(current) : runDir ? folder(runDir) : 'No run selected'}</span>
    <button className={`run-list-button${popup ? ' open' : ''}`} onClick={openWindow}
      title={popup ? 'The run window is open: press to bring it to the front and read the list again.' : 'Opens the run window: every run with its start and finish time, its duration and its results. Choose there which run these tabs show.'}>Runs...</button>
    {popup && root && createPortal(view, root)}
  </>);
}
