/** "Reload saved values" asked by the summary of the rows not saved (record 7.372, `Editors.tsx`): the circuit panel loads the
 *  open task's saved rows again, asking first, as the same button under the toolbar does. */
export const RELOAD_SAVED_REQUEST = 'gator-reload-saved-request';
// Choosing a registered task in the Tasks window (plan-refactoring C9, out of Left.tsx's CircuitPanelBody): its saved rows
// replace the editors' rows - after the user agreed to drop edits -, as one Undo step, and the task load the Runs window uses.
import { MutableRefObject, useEffect, useState } from 'react';
import { api, Json } from '../api';
import { inScope, type Newest, useNewest } from '../newest';
import type { CircuitReference, TaskStarter, TaskSummary, WorkbenchConfig } from '../contracts';
import { noteRowsFrom } from '../store';
import { noRows, sameRows } from './taskRows';

/** The task load the Tasks window uses, for the Runs window's Load run and New run like this (record 7.267; plan "Load run":
 *  "chooseTask becomes one task load that the Tasks and Runs windows both call"). `change` joins the task's rows in the
 *  ONE change of the draft - one Undo step. Not loaded - the edits question answered Cancel, the task could not be read -
 *  nothing changed, and `why` says so in a sentence. */
export type TaskLoaded = { loaded: true } | { loaded: false; why: string };
export type TaskLoad = (taskId: string, change?: (c: WorkbenchConfig) => WorkbenchConfig, stale?: () => boolean) => Promise<TaskLoaded>;

/** `request` (the circuit load's) and `followCount` (the testbench probes'): what a task choice lets go. `load`: the circuit
 *  load. `taskLoad`: filled with this task load for the Runs window, as the panel draws (a write during render, as before). */
export function useTaskChoice({ ref, tasks, latest, setConfig, request, followCount, setCircuit, load, taskLoad }: { ref: CircuitReference; tasks: TaskSummary[];
  latest: MutableRefObject<WorkbenchConfig>; setConfig: (f: (c: WorkbenchConfig) => WorkbenchConfig, record?: boolean) => void; request: Newest; followCount: Newest;
  setCircuit: (c: Json) => void; load: (reference: CircuitReference, follow?: 'choice' | 'press' | null) => Promise<void>;
  taskLoad?: MutableRefObject<TaskLoad | null> }) {
  // Keep the current task and its rows together until the next task is ready. A switch is one Undo step, after any
  // edited rows have been explicitly discarded. Project identity stays; the run label follows the selected task.
  const [taskRows, setTaskRows] = useState<{ task: string; state: 'brought'; starter: TaskStarter } | null>(null);
  const [taskLoading, setTaskLoading] = useState<string | null>(null);
  const [taskLoadError, setTaskLoadError] = useState<string | null>(null);
  const following = useNewest();
  useEffect(() => () => { following.drop(); }, []);
  const starterProblem = (e: any, taskId: string) => (e.status === 404 && taskId.startsWith('real:')
    ? 'This backend is older than the page and has no starting rows for a real task yet: restart it (gator_workbench.cli serve).' : e.message);
  const goneMock = (taskId?: string | null) => !!taskId && taskId.startsWith('synthetic:') && tasks.length > 0 && !tasks.some(t => t.task_key === taskId);
  const removedMock = ref.source === 'registered_task' && goneMock(ref.task_id);
  // `labels`: the class and PDK id of a task just saved (the ngspice window) - not in the task list read before the save.
  // `change`: what else the same draft change brings (Load run: the run's model; record 7.267). True once loaded.
  const chooseTask = async (taskId: string, labels?: { circuit_class?: string | null; pdk_id?: string | null }, reload = false,
    change: (c: WorkbenchConfig) => WorkbenchConfig = c => c, stale: () => boolean = () => false): Promise<TaskLoaded> => {
    const before = latest.current, mine = following.next();
    const currentTask = before.circuit.source === 'registered_task' ? before.circuit.task_id : null;
    // `stale`: the caller's own choice was overtaken (record 7.270: a newer Load run), so this load must not land either.
    const sameTask = inScope({ entity: before.circuit.task_id, revision: before.circuit },
      () => ({ entity: latest.current.circuit.task_id, revision: latest.current.circuit }));
    const stillHere = () => mine() && sameTask() && !stale();
    const brought = taskRows?.task === currentTask ? taskRows!.starter : null;
    setTaskLoadError(null);
    setTaskLoading(taskId);
    try {
      const [previous, starter] = await Promise.all([
        currentTask && currentTask !== taskId ? api.starter(currentTask).catch(() => null) : null,
        api.starter(taskId)]);
      if (!stillHere()) return { loaded: false, why: 'the page changed its task while the saved rows were read' };
      // Check the rows NOW: the user can edit while the read is in flight. A saved-again task may differ from the
      // rows it originally brought; either known baseline counts as untouched when switching to another task.
      const now = latest.current, baseline = currentTask === taskId ? starter : previous;
      const untouched = noRows(now) || sameRows(now, starter) || (!!baseline && sameRows(now, baseline))
        || (!reload && !!brought && sameRows(now, brought));
      if (!untouched && !window.confirm(`${reload ? 'Reload saved values' : `Switch to ${taskId}`}?\n\n`
        + 'This replaces your unsaved Parameters, Probes and Specs edits.\n'
        + 'OK = discard those edits and load the saved rows.\nCancel = keep the current task and edits. You can save them with Save as first.')) return { loaded: false, why: 'you chose Cancel, so the task and its edits stay as they were' };
      if (!stillHere()) return { loaded: false, why: 'another choice came first' };     // the edits question may have taken a while
      const nextCircuit = { ...starter.circuit, ...labels, source: 'registered_task', task_id: taskId };
      setConfig(c => c.circuit !== before.circuit ? c : change({ ...c,
        circuit: nextCircuit,
        project: { ...c.project, task_name: starter.project.task_name },
        parameters: starter.parameters, targets: starter.targets, measurements: starter.measurements }));
      noteRowsFrom(taskId, starter.revision);    // which saved revision these rows are (record 7.203)
      request.drop();                            // any pending circuit view still belongs to the previous task
      followCount.drop();                        // a pending Virtuoso probe read cannot replace the new task's rows
      setCircuit(null);
      if (currentTask === taskId) load(nextCircuit);
      setTaskRows({ task: taskId, state: 'brought', starter });
      return { loaded: true };
    } catch (e: any) {
      if (stillHere()) setTaskLoadError(`Could not load ${taskId}. The current task and rows are unchanged. ${starterProblem(e, taskId)}`);
      return { loaded: false, why: `${taskId} could not be read: ${starterProblem(e, taskId)}` };
    } finally {
      if (mine()) setTaskLoading(null);
    }
  };
  if (taskLoad) taskLoad.current = (taskId, change, stale) => chooseTask(taskId, undefined, false, change, stale);
  return { taskRows, taskLoading, taskLoadError, removedMock, chooseTask };
}
