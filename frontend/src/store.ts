// What the page holds besides its draw (plan-refactoring C3): this file keeps the rows-from note and the task-save signal,
// and is the one place the page and the source fixtures import the rest from - the migrations (migrations.ts), the windows
// of the page (windows.ts), the configuration with its Undo history (history.ts) and the reads (requests.ts).
import type { Json } from './api';
import { CONFIG_KEY } from './contract';
import { signal } from './signal';
import { keep, readKept } from './kept';

export { migrateConfig } from './migrations';
export { pageSeen, registerInputWindow } from './windows';
export { SIMPLE_REWARD, useConfig } from './history';
export { useAsyncAction, usePolling, useRequest } from './requests';

export const STORAGE_KEY = CONFIG_KEY;
/** Which saved revision of which task the editors' rows came from (record 7.203): noted when a task's rows are loaded
 *  (choosing it, Reload saved values) and after each Save task - for this tab, and for the next load of the page. Save
 *  task and the check send it, so rows older than the saved task are not saved over it unasked. */
const ROWS_FROM_KEY = 'gator-workbench-rows-from-v1';
let rowsFromHere: Json = readKept(s => JSON.parse(s.getItem(ROWS_FROM_KEY) ?? 'null'), () => null);
export const rowsFrom = (task: string | null | undefined): number | null =>
  !!task && rowsFromHere?.task === task && Number.isInteger(rowsFromHere?.revision) ? rowsFromHere.revision : null;
export const noteRowsFrom = (task: string, revision: unknown) => {
  if (!Number.isInteger(revision)) return;
  rowsFromHere = { task, revision };
  keep(s => s.setItem(ROWS_FROM_KEY, JSON.stringify(rowsFromHere)));   // no storage: this tab still knows
  noteTaskSaved();
};
/** Saves of the task this page knows of, and saved rows loaded (record 7.222): validation is asked again on each, so the
 *  editors' marks of rows not saved go once Save task has stored them - the rows themselves need not change - and come when
 *  a save from elsewhere left the rows here behind. */
const taskSaves = signal(0);
export const noteTaskSaved = () => { taskSaves.set(taskSaves.get() + 1); };
export const useTaskSaves = () => taskSaves.use();
