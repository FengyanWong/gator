// Links between the windows (record 7.264; plan docs/plan-frontend-run-workflow.md, "What the three windows share"): a task,
// run or model named in another window's Details - or in the run brief - is a link that opens that window AT the item:
// selected, scrolled to, its Details open. One page-wide event per window, which the window's own component listens to;
// the pop-up windows are drawn from this page, so their links dispatch here too. Following a link changes no draft, no
// shown run and no running job. A message in a window that sends the user to the Connection window carries the button to it
// (branch record SIF-108): its event opens that window as it is, as the header's Connection button does.

export const OPEN_RUNS = 'gator-open-runs';
export const OPEN_TASKS = 'gator-open-tasks';
export const OPEN_CONNECTION = 'gator-open-connection';
/** The Runs window at one run, or filtered to one task's runs. `from`: the window the link was pressed in - a pop-up may only
 *  be opened by the window that holds the click (popupWindow.ts). */
export type RunsAt = { run_dir?: string; task_key?: string; from?: Window | null };
export type TasksAt = { task_key?: string; from?: Window | null };   // no task_key: the Tasks window as it is (record 7.372)
export type ConnectionAt = { from?: Window | null };

export const openRunsAt = (at: RunsAt) => window.dispatchEvent(new CustomEvent<RunsAt>(OPEN_RUNS, { detail: at }));
export const openTasksAt = (at: TasksAt) => window.dispatchEvent(new CustomEvent<TasksAt>(OPEN_TASKS, { detail: at }));
/** Opening the Connection window checks nothing (Connection.tsx): a test stays the press of its own button. */
export const openConnection = (from?: Window | null) => window.dispatchEvent(new CustomEvent<ConnectionAt>(OPEN_CONNECTION, { detail: { from } }));
