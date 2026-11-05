import type { Json } from '../api';

export type TaskRuns = { count: number; newest: Json };
const NO_RUNS: TaskRuns = { count: 0, newest: null };

/** Count each task's runs and keep the newest. Equal dates keep the first row, as the stable descending sort did. */
export function summarizeTaskRuns(runs: Json[]) {
  const byTask = new Map<string, TaskRuns>();
  let known = false;
  for (const run of runs) {
    known ||= 'task_key' in run;
    const of = byTask.get(run.task_key);
    if (!of) byTask.set(run.task_key, { count: 1, newest: run });
    else {
      of.count++;
      if (String(run.created_utc ?? '').localeCompare(String(of.newest.created_utc ?? '')) > 0) of.newest = run;
    }
  }
  return { known, of: (key: string): TaskRuns => byTask.get(key) ?? NO_RUNS };
}
