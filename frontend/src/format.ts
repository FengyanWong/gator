// Small text helpers that several windows carried a copy of each (record 7.276): a run folder's own name, and the page's
// times. One place, so the Runs, Tasks and RL model windows, the run brief and the messages cannot drift apart.
import type { RunSummary } from './contracts';

/** A run folder's own name, unique per run: the last part of its path. */
export const folderName = (dir: string) => dir.split(/[\\/]/).filter(Boolean).pop() ?? dir;
/** The same for a file name made from it (an export): "run" when the path has no name. */
export const runName = (runDir: string) => runDir.split(/[\\/]/).filter(Boolean).pop() ?? 'run';
/** Two digits: 7 -> "07". */
export const two = (n: number) => String(n).padStart(2, '0');
/** Local time, in a form that sorts and compares by eye: 2026-09-21 14:03:22. */
export const stamp = (utc?: string | null) => {
  const d = utc ? new Date(utc) : null;
  return d && !Number.isNaN(d.getTime()) ? `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}` : null;
};
/** The time now, as a window says when it last read: 14:03:22. */
export const clock = () => new Date().toLocaleTimeString([], { hour12: false });

// ---- dates and times, as each place writes them (plan-refactoring C8: moved here and named, never merged where the words
// differ; a caller imports one under the name it has always used) ------------------------------------------------------------
// All of them write stamp()'s form, or a part of it, since branch record SIF-59: they wrote the browser's own
// ("16/10/2026, 14:03:22" in an en-GB browser, "20/10, 10:43" in the Compare list) beside the Runs window's "2026-10-20 10:43".
/** A fixed clock time instead of a running "N s ago": nothing re-renders this on a timer, so an age would freeze. The time of
 *  day when it was today, else date and time; a text that is no date as it is (Connection.tsx: when the connection was tested). */
export const timeOrDateTime = (iso: string) => {
  const s = stamp(iso);
  if (!s) return iso;
  return new Date(iso).toDateString() === new Date().toDateString() ? s.slice(11) : s;
};
/** Date and time; a text that is no date is shown as it is (Pdk.tsx: when a PDK was loaded). */
export const dateTimeOrText = (iso: string) => stamp(iso) ?? iso;
/** A fixed clock time of the declaration, in the viewer's local time; null for none (WorkingCopy.tsx). */
export const dateTimeOrNull = (iso?: string | null) => stamp(iso);
/** Date and time, whatever the text: a text that is no date as it is (runWindowActions.ts: when a task was saved again). */
export const dateTime = (since: string) => stamp(since) ?? since;
// The Compare list wrote every run's date at every status update, hidden or not (record 7.279: toLocaleString built a new
// formatter per call, 85 % of the page's work per update; one Intl formatter replaced it). Its labels are kept per row
// since (TrainingTab.tsx's runChoice), and stamp() is a few getters. savedAt and its formatter went too: nothing used them
// since branch record SIF-17.
/** When a run was created, as the Training tab's Compare list and chips write it: "10-20 10:43", as runTitle does (TrainingTab.tsx). */
export const createdAt = (utc?: string | null) => stamp(utc)?.slice(5, 16) ?? 'unknown time';
/** A time of day from seconds since 1970, as the Training tab writes it (its `clock`: format.ts has a clock() of its own). */
export const timeOfDay = (seconds: number) => { const d = new Date(seconds * 1000);   // hh:mm:ss as stamp() writes it (review of SIF-59: a 12-hour browser wrote "02:03:22 PM")
  return Number.isNaN(d.getTime()) ? '' : `${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`; };
/** A run as a message names it: its task and when it was created, "ota7t 10-06 14:02" (the folder's name without a date). */
export const runTitle = (row: RunSummary) => { const d = row.created_utc ? new Date(row.created_utc) : null;
  return d && !Number.isNaN(d.getTime()) ? `${row.task_name ?? folderName(row.run_dir)} ${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}` : folderName(row.run_dir); };

// ---- durations: the run window shows tenths of a second under a minute, the run brief whole seconds ---------------------------
/** A duration as the run window writes it: "12.3 s", "4 min 05 s", "1 h 02 min" (RunList.tsx). */
export const durationTenths = (seconds?: number | null) => {
  if (seconds == null) return null;
  if (seconds < 59.95) return `${seconds.toFixed(1)} s`;
  const t = Math.round(seconds), h = Math.floor(t / 3600);
  return h ? `${h} h ${two(Math.floor(t % 3600 / 60))} min` : `${Math.floor(t / 60)} min ${two(t % 60)} s`;
};
/** A duration as the run brief writes it: "12 s", "4 min 05 s", "1 h 02 min"; nothing for a number that is not finite (RunBrief.tsx). */
export const durationWhole = (seconds?: number | null) => {
  if (seconds == null || !Number.isFinite(seconds)) return null;
  const t = Math.round(seconds), h = Math.floor(t / 3600);
  return h ? `${h} h ${two(Math.floor(t % 3600 / 60))} min` : t >= 60 ? `${Math.floor(t / 60)} min ${two(t % 60)} s` : `${t} s`;
};
/** A run's working time as the Runs window's Duration names it, "so far" while `live`, then - once the rate is known - the
 *  time left: the working time per evaluation used so far, times the evaluations left (branch record SIF-78): "Duration 5 min
 *  01 s so far · about 10 min 02 s left"; null before any working time. The run brief's line, out of RunBrief.tsx so Run
 *  status and the header's run chip say the same (branch record SIF-98: the one number asked for most stood only in that
 *  window). */
export const timeLine = (working: number | null | undefined, used: number | null | undefined, total: number | null | undefined, live: boolean): string | null => {
  const left = live && used && total && working && used > 0 && total > used ? working / used * (total - used) : null;
  return [durationWhole(working) && `Duration ${durationWhole(working)}${live ? ' so far' : ''}`, left != null && `about ${durationWhole(left)} left`]
    .filter(Boolean).join(' · ') || null;
};
/** What timeLine's working time counts, for its tooltip. */
export const TIME_LINE_HELP = 'How long the run was actually working. The time it sat paused is not counted.';

// ---- a run's task and state, as the run window and the Training tab word them -------------------------------------------------
/** A run's task, as the run window names it: its task name, else its task id up to ':', else "unknown task" (RunList.tsx). */
export const runTask = (r: RunSummary) => r.task_name ?? String(r.task_id ?? 'unknown task').split(':')[0];
/** The same in the Training tab: blank without a task id, and no row at all is no error (TrainingTab.tsx). */
export const runTaskOrBlank = (r: RunSummary | null | undefined) => r?.task_name ?? String(r?.task_id ?? '').split(':')[0];
/** A run state's badge in the run window: the class after "state-"; a paused or interrupted run can go on (RunList.tsx). */
export const RUN_STATE_CLASS: Record<string, string> = { completed: 'ok', running: 'busy', starting: 'busy', pausing: 'busy', stopping: 'busy', paused: 'not_ready',
  interrupted: 'not_ready', failed: 'failed', cancelled: 'unknown', stopped: 'unknown' };
/** A run state's badge in the Training tab, as a whole class name: an interrupted run counts as failed there (TrainingTab.tsx). */
export const TRAINING_STATE_CLASS: Record<string, string> = { completed: 'state-ok', failed: 'state-failed', cancelled: 'state-failed', interrupted: 'state-failed',
  running: 'state-busy', starting: 'state-busy', pausing: 'state-busy', stopping: 'state-busy' };
/** A connection's state in words, as the Connection window and its button word it; the Run status tab too since branch record
 *  SIF-54 (it printed the key: "not_applicable"). Out of Connection.tsx, so the run tabs need not import that window. */
export const CONNECTION_STATE: Record<string, string> = {
  ok: 'OK', failed: 'FAILED', not_ready: 'NOT READY', not_applicable: 'n/a', not_checked: 'not checked', busy: 'BUSY', unknown: 'UNKNOWN',
};
/** A part ("layer") of a connection in words, as the Connection window's Details and a launch's question name it (branch
 *  record SIF-55: "Connection layers are UNKNOWN: session_readiness, spectre_license"). The keys are the backend's two
 *  layer lists (connection.py LAYERS, NGSPICE_LAYERS); one this list does not know reads with spaces for its underscores. */
export const LAYER_WORDS: Record<string, string> = { bridge_package: 'bridge package', connection_profile: 'connection settings', tunnel: 'SSH tunnel',
  daemon: 'bridge in Virtuoso', session_readiness: 'Virtuoso session', spectre: 'Spectre', spectre_license: 'Spectre license', ssh: 'SSH login',
  ngspice: 'ngspice program', trial_run: 'test simulation' };
export const layerWords = (layer: string) => LAYER_WORDS[layer] ?? layer.replace(/_/g, ' ');

// ---- numbers (plan-refactoring C10, out of api.ts) ------------------------------------------------------------------------
/** A size in bytes, in the largest binary unit under its size: 512 B, 1.5 KiB, 2.25 GiB. */
export const bytes = (n?: number | null) => n == null ? '-' : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KiB`
  : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MiB` : `${(n / 1073741824).toFixed(2)} GiB`;
/** Why a run stopped, in words (branch record SIF-15: "completed · budget_exhausted"); the key stays in a tooltip. A reason
 *  this list does not know reads with spaces for its underscores. The engine's own pause reads "connection failures", as the
 *  header's chip and line call it (branch record SIF-137: Run status read "infrastructure failures" beside them). */
export const STOP_WORDS: Record<string, string> = { budget_exhausted: 'budget used up', first_feasible: 'first feasible design found',
  wall_time_limit: 'wall-time limit reached', offline_update_budget: 'update budget used up', consecutive_failures: 'too many failures in a row',
  infrastructure_failures: 'connection failures',
  evaluation_exception: 'an evaluation failed', insufficient_storage: 'not enough disk space', baseline_invalid: 'baseline not valid',
  unresolved_launch_intent: 'launch not confirmed', interrupted: 'interrupted', pause: 'paused', user_pause: 'paused by you',
  user_stop: 'stopped by you', exception: 'an error' };
export const stopWords = (reason?: string | null) => (reason ? STOP_WORDS[reason] ?? reason.replace(/_/g, ' ') : '');
/** Where a failed run wrote what went wrong, by its stop reason (branch record SIF-137: the line under the header and Run
 *  status named no place, and every real failure ends there). A run stopped by its failed evaluations wrote each one's
 *  status and diagnostics into the evaluations table and nothing into the errors log. The errors log holds what raised,
 *  and only these reasons say a run ended by it: a crash, an evaluation that raised, the tables' save that failed, a save
 *  point that does not fit (engine.py `_log_error`). Any other failed run is said by its error alone: null (review of
 *  SIF-137: "the rest" sent to an empty errors log a start that failed - no stop reason, the worker wrote its status
 *  before the engine opened its logs, the traceback is in logs/worker.log - and a run whose lanes or schematic were not
 *  restored at its end, its stop reason still "budget used up"; also a full disk and a launch not confirmed). */
const LOGGED_FAILURES = ['exception', 'evaluation_exception', 'persistence_failure', 'checkpoint_incompatible'];
export const failedWhere = (reason?: string | null): 'evaluations' | 'errors' | null => reason === 'consecutive_failures' ? 'evaluations'
  : reason && LOGGED_FAILURES.includes(reason) ? 'errors' : null;
/** That place in words, the same under the header and in Run status. */
export const FAILED_WHERE: Record<'evaluations' | 'errors', string> = {
  evaluations: 'Why each evaluation failed is in Data tables (evaluations: status and diagnostics).',
  errors: 'The details are in the errors log (Logs, errors).' };
/** A number for reading, not for a table's column: three significant digits, no padding - 0.037, -0.0248, 12.3 (branch record
 *  SIF-2: the reward spread was written 0.0370463). */
export const sig = (v: number) => String(Number(v.toPrecision(3)));
// One formatter for every count: toLocaleString makes a new one per call (record 7.279), and counts are written at every
// status update.
const GROUPED = new Intl.NumberFormat('en-US');
/** A count as the whole page writes it (branch record SIF-117): a whole number from 10,000 up in groups of three - "12,000
 *  evaluations", "52,416 parameters" - and a smaller one plain, "6024", as the page wrote every count but two. The RL model
 *  window's facts and the network structure grouped from 1,000 up, so one model's learner updates read "6,024" there and
 *  "6024" in the Training tab and Run status. A number that names one thing (evaluation 35, dispatch #4, a seed, a place on
 *  a chart's axis), a quantity in its unit and a number in a box one types into are no counts and stay as they are.
 *  Anything else as String() writes it. */
export const count = (n: number) => Number.isInteger(n) && Math.abs(n) >= 10000 ? GROUPED.format(n) : String(n);
/** A count with its noun in the right number: "1 blocking issue", "3 blocking issues"; `many` for a plural that is not the
 *  word with an s ("launches"). The header's button read "1 blocking issue(s)" (branch record SIF-45; out of ModelChooser).
 *  The number as `count` writes it (branch record SIF-117). */
export const plural = (n: number, word: string, many = `${word}s`) => `${count(n)} ${n === 1 ? word : many}`;
/** A task's name from a task id as a model or a run records it: "mscr_vco_lin_c:4fd0a8f9303827bd" (the name and its definition's
 *  hash) or "real:mscr_vco_lin_c" -> "mscr_vco_lin_c" (branch record SIF-2). */
export const taskNameOf = (id?: string | null) => String(id ?? '').replace(/^(real|ngspice|synthetic):/, '').split(':')[0] || 'unknown task';
/** A number as the tables write it: whole numbers as they are, others to six significant digits; nothing for none. */
export const num = (v: unknown) => typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toPrecision(6)) : v == null ? '' : String(v);
// ONE way of writing a number in the whole page (review of 2026-09-23: the SI form was written twice, in the corner
// check and in the graph view, with different prefix letters, and the short form twice more).
// `short`: six significant digits without padding - 41.5 and 2.34558e-6, not 41.5000 and 0.00000234558 (device sizes
// are that small). `si` (units.ts): four significant digits, written as every quantity is since record 7.208.
export const short = (v: unknown) => typeof v !== 'number' ? (v == null ? '' : String(v))
  : v !== 0 && (Math.abs(v) < 1e-3 || Math.abs(v) >= 1e6) ? v.toExponential(5).replace(/\.?0+e/, 'e') : String(Number(v.toPrecision(6)));
