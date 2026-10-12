// The Runs window's actions (record 7.267; plan "Load run" and "Existing runs: continued in place"): Load run, New run like
// this, Continue... and Show results, as functions that stay the same for the memoised window. Out of App.tsx's Page
// (plan-refactoring C5).
import { useMemo, useRef, useState } from 'react';
import { api, ApiError, Json, plainError } from '../api';
import { dateTime, folderName, runTitle } from '../format';
import type { Newest } from '../newest';
import type { BottomTab } from '../panels/BottomPanel';
import type { TaskLoad, TaskLoaded } from '../panels/Left';
import { modelNameAt } from '../panels/ModelChooser';
import { MODE_NAME } from '../panels/rlModelText';
import { LOADS, readSavePoint, SavePoint, withSavePoint } from '../savePoint';
import { tasksShared } from '../shared';
import { migrateConfig } from '../store';
import type { RunSettings, RunSummary, TaskRunSummary, WorkbenchConfig } from '../contracts';

/** The run settings New run like this copies (record 7.267; plan "Existing runs: continued in place"): the Mode, the name of the
 *  model it saves, the budget and limits, the seed, the network, the training values, reward and conditions. Not the
 *  connection, the concurrency or the source (that is the save point the run loaded, read from its lineage). The optimizer
 *  is the run's own too, but not one of these (`searchOf`): a configuration names it only when it is not SAC. */
const RUN_SETTINGS = ['model_label', 'max_evaluations', 'max_spectre_launches', 'max_wall_seconds', 'max_retries', 'max_consecutive_failures',
  'max_consecutive_infrastructure_failures', 'stop_at_first_feasible', 'seed', 'frozen_action', 'network', 'reward', 'conditions', 'advanced', 'rehearsal', 'continual_learning'] as const satisfies readonly (keyof RunSettings)[];

/** The optimizer of a run's configuration as a draft holds it (record 7.322): the field when the run was not searched by SAC,
 *  no field for a SAC run - every configuration before record 7.304 was a SAC run and never said so. New run like this left
 *  the draft's own choice standing, so a Bayesian-optimization run repeated from a SAC draft started as a SAC run, without
 *  a word, and a SAC run repeated from a Bayesian draft as a Bayesian one. */
export const searchOf = (settings: RunSettings | null | undefined): Pick<RunSettings, 'optimizer'> =>
  (settings?.optimizer && settings.optimizer !== 'sac' ? { optimizer: settings.optimizer } : {});

/** `followTask` and `loadSerial`: the task-run link's (taskRunFollow.ts): a Load run gives way to a task chosen elsewhere, and its
 *  own task change silences the link. Returns the task load the Project column fills in, Continue...'s ask, and the window's presses. */
export function useRunWindowActions({ config, setConfig, runs, taskKey, followTask, loadSerial, setMessage, setRunDir, setTab, unfold }: {
  config: WorkbenchConfig; setConfig: (next: WorkbenchConfig | ((c: WorkbenchConfig) => WorkbenchConfig), record?: boolean) => void; runs: RunSummary[]; taskKey: string | null;
  followTask: (key: string) => (loaded: boolean) => void; loadSerial: Newest; setMessage: (message: Json) => void; setRunDir: (dir: string | null) => void;
  setTab: (tab: BottomTab) => void; unfold: () => void }) {
  const taskLoad = useRef<TaskLoad | null>(null);
  /** The model a run ended with, pinned: a trained run's newest save point; an Evaluate-only run's the one it evaluated - its
   *  weights never changed -, else its own; a run with no save point (a baseline, one stopped before its first save) the
   *  one it started from. None of these: null, and the model stays as it is. */
  // A save point that is not there (404), or not under the allowed output folders (403), is absent: the next one is tried.
  // Any other failure - the server restarting, a timeout - stops the load, and nothing changes (record 7.270, Astra's review
  // of 2026-10-07: a passing failure used to load the run's parent model instead, and say it had worked).
  const readOrAbsent = (run_dir: string, checkpoint_id: string): Promise<SavePoint | null> =>
    readSavePoint(run_dir, checkpoint_id).catch(e => { if (e instanceof ApiError && (e.status === 404 || e.status === 403)) return null; throw e; });
  const endModel = async (row: TaskRunSummary): Promise<SavePoint | null> => {
    const own = () => readOrAbsent(row.run_dir, 'latest');
    const parent = () => (row.parent?.run_dir && row.parent?.checkpoint_id ? readOrAbsent(row.parent.run_dir, row.parent.checkpoint_id) : Promise.resolve(null));
    return row.mode === 'frozen' ? (await parent()) ?? (await own()) : (await own()) ?? (await parent());
  };
  /** When the run's task was saved again after the run began, or null. */
  const savedSince = async (row: TaskRunSummary): Promise<string | null> => {
    const task = (await tasksShared().catch(() => null))?.tasks?.find(t => t.task_key === row.task_key);
    return task?.saved_utc && row.created_utc && Date.parse(task.saved_utc) > Date.parse(row.created_utc) ? task.saved_utc : null;
  };
  /** The run's task, through the Tasks window's task load, with `change` in its one draft change; when it is the page's task
   *  already, `change` alone - the editors stay as they are, edits included. The task-run link (7.212) gives way: this task
   *  change comes with its run, and the caller decides what the bottom tabs show. */
  const withRunTask = async (row: TaskRunSummary, change: (c: WorkbenchConfig) => WorkbenchConfig, changes: boolean, stale: () => boolean): Promise<TaskLoaded> => {
    if (stale()) return { loaded: false, why: 'another choice came first' };
    if (taskKey === row.task_key) { if (changes) setConfig(change); return { loaded: true }; }
    const settle = followTask(row.task_key);
    const result = await (taskLoad.current?.(row.task_key, change, stale) ?? Promise.resolve<TaskLoaded>({ loaded: false, why: 'the task panel is not ready yet' }));
    settle(result.loaded);
    return result;
  };
  const nameOf = (point: SavePoint) => modelNameAt(runs, point.run_dir);
  const sinceText = (since: string | null, what: string) => since
    ? ` The task was saved again after ${what} began (${dateTime(since)}): the RL model window's check says whether the model still fits.` : '';
  /** Load run: its task, the model it ended with (in a Mode that loads one) and its results - one Undo step for the task and
   *  the model, all or nothing. The header's run is never touched. True once loaded - the Runs window then closes (user
   *  request 2026-10-09) -, false when nothing changed: Cancel at the edits question, an unreadable model, a newer choice. */
  const loadRun = async (row: TaskRunSummary): Promise<boolean> => {
    const mine = loadSerial.next(), stale = () => !mine();      // a newer choice wins, silently
    setMessage(null);
    let point: SavePoint | null, since: string | null;
    try { [point, since] = await Promise.all([endModel(row), savedSince(row)]); }
    catch (e: any) {
      if (!stale()) setMessage({ level: 'error', text: `Run ${runTitle(row)} was not loaded: its model could not be read (${plainError(e)}). Nothing changed.` });
      return false;
    }
    if (stale()) return false;
    const mode = LOADS.includes(config.run.mode) ? config.run.mode : 'fine_tune';
    const same = taskKey === row.task_key;
    const result = await withRunTask(row, c => (point ? { ...c, run: withSavePoint({ ...c.run, mode: LOADS.includes(c.run.mode) ? c.run.mode : 'fine_tune' }, point) } : c), !!point, stale);
    if (stale()) return false;
    if (!result.loaded) { setMessage({ level: 'info', text: `Run ${runTitle(row)} was not loaded: ${result.why}. Nothing changed.` }); return false; }
    setRunDir(row.run_dir); setTab('status'); unfold();
    setMessage({ level: 'info', text: `Loaded run ${runTitle(row)}: task ${row.task_key}${same ? ' (already on the page: the editors stay as they were)' : ''}, `
      + (point ? `${MODE_NAME[mode]} from ${nameOf(point)} @ ${point.evaluations ?? point.checkpoint_id}.` : 'the model as it was: this run has no save point and loaded none.')
      + `${sinceText(since, 'this run')} Undo takes it back.` });
    return true;
  };
  /** New run like this: the next run repeats the run - its task, Mode, the save point it started from and its run settings.
   *  The shown run stays. True once taken (the Runs window then closes), false when nothing changed. */
  const newRunLike = async (row: TaskRunSummary): Promise<boolean> => {
    const mine = loadSerial.next(), stale = () => !mine();
    setMessage(null);
    let settings: RunSettings | null = null;
    try { settings = migrateConfig(await api.runConfig(row.run_dir))?.run ?? null; }
    catch (e: any) { if (!stale()) setMessage({ level: 'error', text: `New run like ${runTitle(row)}: its configuration could not be read (${e.message}). Nothing changed.` }); return false; }
    if (stale()) return false;
    if (!settings) { setMessage({ level: 'error', text: `New run like ${runTitle(row)}: the run has no configuration of its own. Nothing changed.` }); return false; }
    // A run continued under the old Mode resume repeats as what it was: a fine-tune of its model, or a new model.
    const mode = settings.mode === 'resume' ? (row.parent?.run_dir ? 'fine_tune' : 'scratch') : settings.mode;
    const from = LOADS.includes(mode) ? row.parent : null;
    const [point, since] = await Promise.all([from?.run_dir && from?.checkpoint_id ? readSavePoint(from.run_dir, from.checkpoint_id).catch(() => null) : Promise.resolve(null), savedSince(row)]);
    if (stale()) return false;
    const copied = Object.fromEntries(RUN_SETTINGS.filter(k => k in settings).map(k => [k, settings[k]]));
    const search = searchOf(settings);
    const result = await withRunTask(row, c => {
      const { optimizer: _draft, ...kept } = c.run;                  // the run's optimizer, never the draft's (searchOf)
      const run = { ...kept, ...copied, ...search, mode };
      return { ...c, run: point ? withSavePoint(run, point) : { ...run, model_source: { ...(c.run.model_source ?? {}),
        run_dir: from?.run_dir ?? null, checkpoint_id: from?.run_dir ? from.checkpoint_id ?? 'latest' : 'latest' } } };
    }, true, stale);
    if (stale()) return false;
    if (!result.loaded) { setMessage({ level: 'info', text: `New run like ${runTitle(row)}: not taken, ${result.why}. Nothing changed.` }); return false; }
    setMessage({ level: 'info', text: `The next run repeats ${runTitle(row)}: task ${row.task_key}, ${MODE_NAME[mode] ?? mode}`
      + (search.optimizer === 'bayes' ? ' searched by Bayesian optimization (the network is neither asked nor trained)' : search.optimizer ? ` searched by ${search.optimizer}` : '')
      + (from ? ` from ${point ? `${nameOf(point)} @ ${point.evaluations ?? point.checkpoint_id}` : `${folderName(from.run_dir)}'s save point ${from.checkpoint_id} (it could not be read now)`}` : '')
      + `, ${settings.max_evaluations} evaluations, seed ${settings.seed}, with its network, training values, reward, conditions and limits.`
      + `${sinceText(since, 'that run')} A model name already taken gets a number at the start. Undo takes it back.` });
    return true;
  };
  /** Continue... of the Runs window: the run is shown under Run status with its budget form open, where it goes on. */
  const [askContinue, setAskContinue] = useState<{ runDir: string; serial: number } | null>(null);
  const continueFrom = (row: TaskRunSummary) => { setRunDir(row.run_dir); setTab('status'); unfold(); setAskContinue(a => ({ runDir: row.run_dir, serial: (a?.serial ?? 0) + 1 })); };
  // The Runs window's actions as functions that stay the same and call the page's latest ones (record 7.279): with new
  // functions at every render, the memoised window was drawn again at every status update.
  const runActions = useRef({ loadRun, newRunLike, continueFrom, setRunDir, unfold });
  runActions.current = { loadRun, newRunLike, continueFrom, setRunDir, unfold };
  const runWindow = useMemo(() => ({
    choose: (dir: string | null) => { runActions.current.setRunDir(dir); if (dir) runActions.current.unfold(); },
    load: (row: TaskRunSummary) => runActions.current.loadRun(row),
    newLike: (row: TaskRunSummary) => runActions.current.newRunLike(row),
    continueFrom: (row: TaskRunSummary) => runActions.current.continueFrom(row),
  }), []);
  return { taskLoad, askContinue, runWindow };
}
