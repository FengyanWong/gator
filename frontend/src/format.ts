// Small text helpers that several windows carried a copy of each (record 7.276): a run folder's own name, and the page's
// times. One place, so the Runs, Tasks and RL model windows, the run brief and the messages cannot drift apart.

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
/** A fixed clock time instead of a running "N s ago": nothing re-renders this on a timer, so an age would freeze. The time of
 *  day when it was today, else date and time (Connection.tsx: when the connection was tested). */
export const timeOrDateTime = (iso: string) => {
  const at = new Date(iso);
  return at.toDateString() === new Date().toDateString() ? at.toLocaleTimeString() : at.toLocaleString();
};
/** Date and time in the viewer's words; a text that is no date is shown as it is (Pdk.tsx: when a PDK was loaded). */
export const dateTimeOrText = (iso: string) => { const at = new Date(iso); return isNaN(+at) ? iso : at.toLocaleString(); };
/** A fixed clock time of the declaration, in the viewer's local time; null for none (WorkingCopy.tsx). */
export const dateTimeOrNull = (iso?: string | null) => { const d = iso ? new Date(iso) : null; return d && !Number.isNaN(d.getTime()) ? d.toLocaleString() : null; };
/** Date and time in the viewer's words, whatever the text: "Invalid Date" for none (App.tsx: when a task was saved again). */
export const dateTime = (since: string) => new Date(since).toLocaleString();
// One formatter (record 7.279): toLocaleString built one per call, for every saved model at every keystroke while the
// RL model window was open.
const WHEN = new Intl.DateTimeFormat(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' });
/** When a save point or a saved model was saved: "09 Oct, 12:00:00" (ModelChooser.tsx). */
export const savedAt = (utc?: string | null) => { const d = utc ? new Date(utc) : null;
  return d && !Number.isNaN(d.getTime()) ? WHEN.format(d) : 'unknown time'; };
// One formatter for every date (record 7.279): toLocaleString built a new one per call, and the Compare list formatted
// every run's date at every status update - 85 % of the page's work per update, even with the tab hidden.
const CREATED = new Intl.DateTimeFormat([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
/** When a run was created, as the Training tab's Compare list writes it (TrainingTab.tsx). */
export const createdAt = (utc?: string | null) => {
  if (!utc) return 'unknown time';
  const d = new Date(utc);
  return Number.isNaN(d.getTime()) ? 'Invalid Date' : CREATED.format(d);         // what toLocaleString said for it
};
/** A time of day from seconds since 1970, as the Training tab writes it (its `clock`: format.ts has a clock() of its own). */
export const timeOfDay = (seconds: number) => new Date(seconds * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
/** A run as a message names it: its task and when it was created, "ota7t 10-06 14:02" (the folder's name without a date). */
export const runTitle = (row: any) => { const d = row.created_utc ? new Date(row.created_utc) : null;
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

// ---- a run's task and state, as the run window and the Training tab word them -------------------------------------------------
/** A run's task, as the run window names it: its task name, else its task id up to ':', else "unknown task" (RunList.tsx). */
export const runTask = (r: any) => r.task_name ?? String(r.task_id ?? 'unknown task').split(':')[0];
/** The same in the Training tab: blank without a task id, and no row at all is no error (TrainingTab.tsx). */
export const runTaskOrBlank = (r: any) => r?.task_name ?? String(r?.task_id ?? '').split(':')[0];
/** A run state's badge in the run window: the class after "state-"; a paused or interrupted run can go on (RunList.tsx). */
export const RUN_STATE_CLASS: Record<string, string> = { completed: 'ok', running: 'busy', starting: 'busy', pausing: 'busy', stopping: 'busy', paused: 'not_ready',
  interrupted: 'not_ready', failed: 'failed', cancelled: 'unknown', stopped: 'unknown' };
/** A run state's badge in the Training tab, as a whole class name: an interrupted run counts as failed there (TrainingTab.tsx). */
export const TRAINING_STATE_CLASS: Record<string, string> = { completed: 'state-ok', failed: 'state-failed', cancelled: 'state-failed', interrupted: 'state-failed',
  running: 'state-busy', starting: 'state-busy', pausing: 'state-busy', stopping: 'state-busy' };

// ---- numbers (plan-refactoring C10, out of api.ts) ------------------------------------------------------------------------
/** A size in bytes, in the largest binary unit under its size: 512 B, 1.5 KiB, 2.25 GiB. */
export const bytes = (n?: number | null) => n == null ? '-' : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KiB`
  : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MiB` : `${(n / 1073741824).toFixed(2)} GiB`;
/** Why a run stopped, in words (branch record SIF-15: "completed · budget_exhausted"); the key stays in a tooltip. A reason
 *  this list does not know reads with spaces for its underscores. */
export const STOP_WORDS: Record<string, string> = { budget_exhausted: 'budget used up', first_feasible: 'first feasible design found',
  wall_time_limit: 'wall-time limit reached', offline_update_budget: 'update budget used up', consecutive_failures: 'too many failures in a row',
  evaluation_exception: 'an evaluation failed', insufficient_storage: 'not enough disk space', baseline_invalid: 'baseline not valid',
  unresolved_launch_intent: 'launch not confirmed', interrupted: 'interrupted', pause: 'paused', user_pause: 'paused by you',
  user_stop: 'stopped by you', exception: 'an error' };
export const stopWords = (reason?: string | null) => (reason ? STOP_WORDS[reason] ?? reason.replace(/_/g, ' ') : '');
/** A number for reading, not for a table's column: three significant digits, no padding - 0.037, -0.0248, 12.3 (branch record
 *  SIF-2: the reward spread was written 0.0370463). */
export const sig = (v: number) => String(Number(v.toPrecision(3)));
/** A count with its noun in the right number: "1 blocking issue", "3 blocking issues"; `many` for a plural that is not the
 *  word with an s ("launches"). The header's button read "1 blocking issue(s)" (branch record SIF-45; out of ModelChooser). */
export const plural = (n: number, word: string, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;
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
