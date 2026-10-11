// The task's own presses in the Project column (plan-refactoring C9, out of Left.tsx's CircuitPanelBody): Check now, Delete
// task (a saved task or an ngspice task), and which launchers the connection in use offers.
import { MutableRefObject, useEffect, useState } from 'react';
import { api, Json, problemText } from '../api';
import { connectionProfilesShared, tasksShared } from '../shared';
import { useAsyncAction, useRequest } from '../store';
import { gateText } from './CircuitBrowser';
import type { TaskLoaded } from './taskChoice';

/** `ref` / `virtuosoOn`: the configuration's circuit and whether the page follows a Virtuoso cell (CircuitPanelBody's). */
export function useTaskActions({ ref, virtuosoOn, config, setConfig, circuit, profileId, tasks, setTasks, latest, refreshTasks, chooseTask }: {
  ref: Json; virtuosoOn: boolean; config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; circuit: Json; profileId: string | null;
  tasks: Json[]; setTasks: (tasks: Json[]) => void; latest: MutableRefObject<Json>; refreshTasks: () => Promise<unknown>;
  chooseTask: (taskId: string) => Promise<TaskLoaded> }) {
  // A saved task: "Check now" runs the check Start runs by itself before every run (backend consistency.py - the editors,
  // the task file and the cell in Virtuoso must agree; the run adapter connects and exports without simulating). A
  // finished Baseline simulation records its result as the task's reference by itself (status record 7.78; the
  // manual "Record the baseline run as reference" went on 2026-09-29). Explicit presses, none starts a simulation.
  // A check result goes as soon as the rows change: it was about the rows before. A message says which press it answers
  // (`what`): the answer to Delete task stands by that button in the Tasks window.
  const [taskCheck, setTaskCheck] = useState<Json>(null);
  const [profileMessage, setProfileMessage] = useState<Json>(null);
  const generatedName = ref.source === 'registered_task' && circuit?.generated_profile ? String(ref.task_id ?? '').replace(/^real:/, '') : null;
  // Delete task is offered for a generated task (real:<name>, saved from a cell) whether it is loaded or blocked - one
  // that no longer passes its checks is one to start over from; the task list says which tasks are generated.
  const deletableName = generatedName ?? (ref.source === 'registered_task' && tasks.find(t => t.task_key === ref.task_id)?.generated
    ? String(ref.task_id ?? '').replace(/^real:/, '') : null);
  useEffect(() => { setTaskCheck(null); setProfileMessage(null); }, [generatedName]);
  const rowsKey = (c: Json) => JSON.stringify([c.parameters, c.measurements, c.targets]);
  useEffect(() => { setTaskCheck(null); }, [rowsKey(config)]);
  const { busy: profileBusy, run: profileAction } = useAsyncAction((e, what) =>
    setProfileMessage({ level: 'error', what, text: problemText(e, gateText) }), () => setProfileMessage(null));
  // The check takes seconds (it connects and exports): an answer about rows or a task that changed meanwhile is not
  // shown as the answer about the ones on the page now.
  const checkTask = () => {
    const rows = rowsKey(config), task = ref.task_id;
    profileAction('check', async () => {
      const answer = await api.taskCheck(profileId, config);
      if (rowsKey(latest.current) === rows && latest.current.circuit.task_id === task) setTaskCheck(answer);
      else setProfileMessage({ level: 'warn', what: 'check', text: 'The rows or the task changed while the check ran: press "Check now" again.' });
    });
  };
  // Delete task: takes a saved task out of the list. Asked once more, because the task leaves the list. The backend keeps
  // the files aside and refuses while a run of the task is working. The page then follows the cell the task was saved
  // from, which is free again for a new task.
  const [deleted, setDeleted] = useState<Json>(null);
  const deleteProfile = (owner: Window) => {
    if (!owner.confirm(`Delete the task real:${deletableName}?\n\nIt leaves the Registered task list, and its cell can get a new task. Runs already made `
      + 'with it keep their data, but a paused one can no longer be resumed. A copy of the task\'s files is kept on the backend machine; the '
      + 'cell in Virtuoso stays as it is, its Maestro test included.'
      + (circuit?.baseline_recorded ? '\n\nIts recorded baseline goes with it: a new task needs a new real baseline simulation.' : ''))) return;
    const task = ref.task_id;
    // The page follows the deleted task's cell only while it still shows that task (record 7.322). A task loaded while the
    // deletion ran keeps its circuit: the answer used to put the deleted task's cell under the new task's rows.
    const shows = (c: Json) => c.circuit?.source === 'registered_task' && c.circuit?.task_id === task;
    profileAction('delete', async () => {
      const gone = await api.deleteProfile(deletableName!);
      setDeleted(gone);
      refreshTasks();
      if (!shows(latest.current)) setProfileMessage({ level: 'ok', what: 'delete', text: `Task ${task} deleted. The page stays on what was chosen meanwhile.` });
      setConfig(c => (shows(c) ? { ...c, circuit: { ...c.circuit, source: 'virtuoso', task_id: null, library: gone.library, cell: gone.cell, view: 'schematic', testbench_cell: gone.testbench_cell ?? null } } : c));
    });
  };
  const deletedHere = deleted && virtuosoOn && deleted.library === ref.library && deleted.cell === ref.cell ? deleted : null;
  // The launchers follow the connection in use (user request 2026-09-23): a Virtuoso connection shows "Virtuoso cell..."
  // only, an ngspice connection "ngspice netlist..." only; no connection (or one of a kind this page does not know) shows
  // both. The family is read from the profile list - the workbench's own file, no probe - when the connection changes.
  const { value: family } = useRequest<string>(() => connectionProfilesShared()
    .then(p => (p.profiles ?? []).find((x: Json) => x.profile_id === profileId)?.family ?? null), [profileId], { enabled: !!profileId });
  const showVirtuoso = family !== 'ngspice', showNgspice = family !== 'virtuoso';
  // The task window follows the same rule for the ngspice tasks (user request 2026-09-24: the ngspice OTA example is to show
  // only while ngspice is connected): while a Virtuoso connection is in use they are listed with the mark "choose its
  // connection" (the old drop-down left them out; the window shows every task, record 7.227).
  // An ngspice netlist task (Ngspice.tsx saves it; the page then follows it). Delete takes it out of the list: its folder
  // is kept aside on the backend machine, and the page follows the first task left (the rows stay unless untouched).
  const ngspiceTask = ref.source === 'registered_task' && /^ngspice:/.test(ref.task_id ?? '') ? String(ref.task_id).slice('ngspice:'.length) : null;
  const deleteNgspice = (owner: Window) => {
    if (!owner.confirm(`Delete the task ngspice:${ngspiceTask}?\n\nIt leaves the Registered task list. Runs already made with it keep their data, `
      + 'but a paused one can no longer be resumed. Its deck and task file are kept aside on the backend machine.')) return;
    const task = ref.task_id;
    profileAction('delete', async () => {
      const gone = await api.ngspiceDelete(ngspiceTask!);
      const left = await tasksShared(true).then(t => { setTasks(t.tasks); return t.tasks; }).catch(() => [] as Json[]);
      setProfileMessage({ level: 'ok', what: 'delete', text: `Task ${gone.deleted} deleted; its files are kept in ${gone.kept_copy}.` });
      // The first task left is taken only while the page still shows the deleted one (record 7.322): a task chosen while
      // the deletion ran stays.
      const next = left.find((t: Json) => t.task_key !== gone.deleted);
      if (next && latest.current.circuit?.task_id === task) chooseTask(next.task_key);
    });
  };
  return { taskCheck, profileMessage, generatedName, deletableName, profileBusy, checkTask, setDeleted, deleteProfile, deletedHere, showVirtuoso,
    showNgspice, ngspiceTask, deleteNgspice };
}
