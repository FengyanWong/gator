import { migrateConfig, noteRowsFrom, useAsyncAction, useRequest } from '../store';
import { CircuitDetails, gateText, namedTestbench, NativeSchematic, useVirtuosoBrowser } from './CircuitBrowser';
import { Icon } from './Icons';
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, connectionProfilesShared, Json, problemText } from '../api';
import { BLOCKED, usePopupWindow } from './popupWindow';
import { PdkWindowButton, pdksChanged } from './Pdk';
import { WorkingCopy } from './WorkingCopy';
import { NgspiceButton } from './Ngspice';
import { TaskSave } from './TaskSave';
import { TaskListButton, taskMark } from './TaskList';
import { CheckSteps } from './Consistency';
import { Typed } from './Typed';
import { CircuitPicture } from './CircuitPicture';

/** The connection block lives in Connection.tsx: one button in this column that opens the connection window. */

/** The left column holds the Project fields and the REGISTERED TASK only (user request 2026-09-23). Reading a cell from
 *  Virtuoso - library / cell / testbench, the read, the task's first save - lives in a window of its
 *  own behind ONE button, "Virtuoso cell..." (the mechanism of the connection window: a portal into a named pop-up).
 *  An ngspice netlist (a SPICE deck pasted or loaded from a file) becomes a task the same way, behind "ngspice netlist..."
 *  (Ngspice.tsx): such a task runs on an ngspice connection and needs no Virtuoso.
 *  The workbench makes no working copy of its own any more: reading a cell asks whether it is a copy the user made, and
 *  then works in THAT cell (the backend records it as the cell's working copy: import with `work_here`). */

/** The circuit sources: a registered task (the column) and a Virtuoso cell (the window). "Import Spectre netlist" was
 *  removed (user request, status record 7.53): a configuration saved before still names `netlist`; the column then says so. */
const SOURCES = ['registered_task', 'virtuoso'];
/** A dropdown must be able to show the configured value even when the list does not (yet) contain it. */
const withCurrent = (names: string[], current?: string | null) => (current && !names.includes(current) ? [current, ...names] : names);
const sameJson = (a: Json, b: Json) => JSON.stringify(a ?? []) === JSON.stringify(b ?? []);

/** The three editors, by their configuration keys: Parameters, Specs, Probes. */
const ROW_SECTIONS = ['parameters', 'targets', 'measurements'];
/** The three tables as a reload leaves them (store.ts migrateConfig), for comparing: a task saved before a column retired
 *  still carries it (`tolerance: 0` on every spec of mscr_ota7t/ring3/vco_lin) and the page drops it when it reloads, so
 *  the rows compared as they came never matched again - switching task asked to discard edits nobody made (record 7.223).
 *  Both sides, as rows on the page can carry a retired field too (an answer that still names one). */
const tablesOf = (config: Json): Json => migrateConfig(Object.fromEntries(ROW_SECTIONS.map(s => [s, config?.[s] ?? []])));
const sameRows = (config: Json, starter: Json) => { const a = tablesOf(config), b = tablesOf(starter); return ROW_SECTIONS.every(s => sameJson(a[s], b[s])); };
const noRows = (config: Json) => ROW_SECTIONS.every(s => !(config[s] ?? []).length);

/** Asked before a cell is read (window.confirm, the project's confirmation style): the workbench writes into the cell it
 *  reads, so it has to be a copy the user made. OK = read it and work in it; Cancel = read nothing. */
const copyQuestion = (r: Json) => `Work in ${r.library}/${r.cell} directly?\n\n`
  + 'The workbench makes no copy of its own. It writes into the cell it reads: saving a task writes the Maestro test GATOR into '
  + `${r.testbench_cell ? `the testbench ${r.testbench_cell}` : 'its testbench'}, and every run sets device sizes in ${r.cell} (put back when the run `
  + 'ends; a forced abort can leave them changed).\n\n'
  + 'So only read a COPY you made in Virtuoso (Library Manager: copy the cell and its testbench into a library of yours).\n\n'
  + `OK = ${r.library}/${r.cell} is such a copy: read it and work in it.\nCancel = read nothing.`;

/** The header's title block (record 7.158): what the page works on, as a drawing names its subject - the saved task's
 *  revision, the circuit's class and PDK labels, and the label the RL model is saved under (record 7.159: it took the
 *  project name's place). Read-only; the fields themselves stay in their panels. */
function TitleFacts({ config, revision }: { config: Json; revision: number | string | null }) {
  const ref = config.circuit;
  // No task name here (record 7.182, user: "remove the current task name on the header"): the Project column's Task list
  // names it; the revision of the saved task stays.
  const model = (config.run.model_label ?? '').trim() || config.project.task_name;
  const fact = (key: string, value: string, extra = '') => <span className={`tb-cell${extra}`}><span className="tb-k">{key}</span><span className="tb-v" title={value}>{value}</span></span>;
  return <>{fact('Rev', revision == null ? '-' : String(revision), ' tb-rev')}
    {fact('Class · PDK', `${ref.circuit_class ?? 'unspecified'} · ${ref.pdk_id ?? 'unspecified'}`)}{fact('RL model', model, ' tb-model')}</>;
}

export function CircuitPanel({ config, setConfig, circuit, setCircuit, profileId, taskSlot, taskNotes, titleSlot = null, taskEpoch = 0, runs = [], refreshRuns }:
  { config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; circuit: Json; setCircuit: (c: Json) => void; profileId: string | null;
    taskSlot: HTMLElement | null; taskNotes: HTMLElement | null;
    titleSlot?: HTMLElement | null; taskEpoch?: number; runs?: Json[]; refreshRuns?: () => Promise<Json[]> }) {
  const [tasks, setTasks] = useState<Json[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [nativeOpen, setNativeOpen] = useState(false);                    // closed until asked for; the choice then lasts across cells and Refresh
  const [hierarchyOpen, setHierarchyOpen] = useState(false);              // the whole Hierarchy block is one closed line; same rule
  const ref = config.circuit;
  const offered = SOURCES.includes(ref.source);     // false: a saved configuration names the removed netlist source
  const virtuosoOn = ref.source === 'virtuoso';     // the page follows a Virtuoso cell (the window's work), not a task
  // The window's own choice: what the configuration says while the page follows a Virtuoso cell; blank while it follows a
  // task. A library chosen in the window then switches the page to the cell, as choosing the source used to.
  const chosen: Json = virtuosoOn ? ref : { library: null, cell: null, testbench_cell: null };
  const request = useRef(0);                        // only the newest load may answer
  const followNext = useRef<'choice' | 'press' | null>(null);   // the next load answers a choice or a Read press: Probes may follow it
  const latest = useRef(config);                    // the configuration as it is NOW, for answers that arrive later
  latest.current = config;
  const patch = (fields: Json, follow: 'choice' | 'press' | null = null) => {
    if (follow) followNext.current = follow;
    setConfig(c => ({ ...c, circuit: { ...c.circuit, ...fields } }));
  };
  // The Virtuoso window: one named pop-up, drawn through a portal (popupWindow.ts, as the connection window is).
  const { popup, root, blocked, open: openWindow } = usePopupWindow('gator-virtuoso',
    { title: 'GATOR - Virtuoso cell', features: 'popup,width=720,height=980', rootId: 'virtuoso-root' });

  useEffect(() => { api.tasks().then(t => setTasks(t.tasks)).catch(e => setError(e.message)); }, []);
  // follow: 'choice' (a library / cell / testbench was chosen) or 'press' (the cell was read): a Virtuoso draft that loads
  // then brings the Probes of the testbench it was read through (followTestbench).
  const load = async (reference: Json, follow: 'choice' | 'press' | null = null) => {
    const mine = ++request.current;
    setError(null);
    try {
      const loaded = await api.loadCircuit(reference);
      if (mine === request.current) { setCircuit(loaded); if (follow) followTestbench(loaded, follow === 'press'); }
    }
    catch (e: any) { if (mine === request.current) { setError(e.message); setCircuit(null); } }
  };
  // A registered task loads on its task alone: the Virtuoso fields the configuration still carries (the last cell read)
  // mean nothing to it, so a library or cell chosen in the window does not reload the task. The labels (circuit class,
  // PDK id) change nothing the backend reads: typing them reloaded the task at every keystroke (audit 2026-09-30).
  const loadKey = JSON.stringify({ ...(virtuosoOn ? ref : { ...ref, library: null, cell: null, view: null, testbench_cell: null }), circuit_class: null, pdk_id: null });
  const loadedAs = useRef<string | null>(null);
  useEffect(() => {
    const follow = followNext.current;
    followNext.current = null;
    // The removed netlist source is not sent to the backend (which refuses it): the column says so and waits for a
    // choice. Whatever was loaded before no longer belongs to this reference, so it is cleared.
    if (!offered) { request.current++; setError(null); setCircuit(null); return; }
    // Another task - or the first look - loads at once. A change within the same one waits 0.4 s to settle: arrowing
    // through the Cell list of the Virtuoso window chose every cell on the way, and a cell's load may ask the bridge.
    // The previous cell's load still on its way is no longer this reference's: its answer was shown under the new cell
    // during those 0.4 s (review of 2026-10-01).
    request.current++;
    const task = `${ref.source}|${ref.task_id}`, settle = loadedAs.current === task ? 400 : 0;
    const timer = setTimeout(() => { loadedAs.current = task; load(ref, follow && virtuosoOn ? follow : null); }, settle);
    return () => clearTimeout(timer);
  }, [loadKey]);
  // A run that came to rest in the header may have changed what the task knows about itself - a finished Single baseline
  // simulation records the task's reference by itself (status record 7.78) - so the task is read again: local files, free.
  useEffect(() => { if (taskEpoch && offered && ref.source === 'registered_task') load(ref); }, [taskEpoch]);

  const { native, libraries, cells, chosenCell, listing, nativeError, setNativeError, nativeProblem, setRefresh } =
    useVirtuosoBrowser(!!popup, profileId, chosen, setConfig);
  // Save task (TaskSave.tsx): the editors' rows become the task real:<name>, which runs in the cell that was read. After a
  // first save the column switches to the task; after saving the open task again it is loaded again (its baseline may no
  // longer hold).
  const [saved, setSaved] = useState<Json>(null);          // the last first save: said again once the task is open
  const refreshTasks = () => api.tasks().then(t => setTasks(t.tasks)).catch(() => undefined);
  const taskSaved = (made: Json, sentConfig: Json) => {
    if (latest.current.circuit !== sentConfig.circuit) return;
    setDeleted(null); setSaved(made.created ? made : null);
    refreshTasks();
    const parameters = (c: Json) => c.parameters === sentConfig.parameters ? made.parameters : c.parameters;
    if (made.task_key === sentConfig.circuit.task_id) {
      setConfig(c => c.circuit === sentConfig.circuit ? { ...c, parameters: parameters(c) } : c);
      load(sentConfig.circuit); return;
    }
    setConfig(c => c.circuit !== sentConfig.circuit ? c : ({ ...c, parameters: parameters(c),
      project: { ...c.project, task_name: made.task_key.replace(/^[^:]+:/, '') },
      circuit: { ...c.circuit, source: 'registered_task', task_id: made.task_key, circuit_class: made.circuit_class, pdk_id: made.pdk_id } }));
  };
  // A save the page followed but did not send (record 7.198: sent before the page was loaded again, or from another tab):
  // the task list and the open task are read again; the rows stay as they are, and the check says if they differ.
  const savedElsewhere = (last: Json) => {
    refreshTasks();
    if (last.ok && last.task_key === latest.current.circuit.task_id) load(latest.current.circuit);
  };
  // A saved task: "Check now" runs the check Start runs by itself before every run (backend consistency.py - the editors,
  // the task file and the cell in Virtuoso must agree; the run adapter connects and exports without simulating). A
  // finished Baseline simulation records its result as the task's reference by itself (status record 7.78; the
  // manual "Record the baseline run as reference" went on 2026-09-29). Explicit presses, none starts a simulation.
  // A check result goes as soon as the rows change: it was about the rows before. A message says which press it answers
  // (`what`): the answer to Delete task stands by that button, in the task row at the top of the column.
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
  const deleteProfile = () => {
    if (!window.confirm(`Delete the task real:${deletableName}?\n\nIt leaves the Registered task list, and its cell can get a new task. Runs already made `
      + 'with it keep their data, but a paused one can no longer be resumed. A copy of the task\'s files is kept on the backend machine; the '
      + 'cell in Virtuoso stays as it is, its Maestro test included.'
      + (circuit?.baseline_recorded ? '\n\nIts recorded baseline goes with it: a new task needs a new real baseline simulation.' : ''))) return;
    profileAction('delete', async () => {
      const gone = await api.deleteProfile(deletableName!);
      setDeleted(gone);
      refreshTasks();
      setConfig(c => ({ ...c, circuit: { ...c.circuit, source: 'virtuoso', task_id: null, library: gone.library, cell: gone.cell, view: 'schematic', testbench_cell: gone.testbench_cell ?? null } }));
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
  const deleteNgspice = () => {
    if (!window.confirm(`Delete the task ngspice:${ngspiceTask}?\n\nIt leaves the Registered task list. Runs already made with it keep their data, `
      + 'but a paused one can no longer be resumed. Its deck and task file are kept aside on the backend machine.')) return;
    profileAction('delete', async () => {
      const gone = await api.ngspiceDelete(ngspiceTask!);
      const left = await api.tasks().then(t => { setTasks(t.tasks); return t.tasks; }).catch(() => [] as Json[]);
      setProfileMessage({ level: 'ok', what: 'delete', text: `Task ${gone.deleted} deleted; its files are kept in ${gone.kept_copy}.` });
      const next = left.find((t: Json) => t.task_key !== gone.deleted);
      if (next) chooseTask(next.task_key);
    });
  };
  // Reading a cell INTO the workbench is an explicit press: Virtuoso exports the netlist of the testbench (or of the cell)
  // and the sizes are read back - read-only, zero-cost, some seconds. The first read of a cell asks whether it is a copy
  // the user made (copyQuestion): "OK" reads it AND makes it the cell the task flow works in (import with work_here; the
  // backend records it as the cell's working copy). Reading a cell that already is that cell asks nothing.
  const [importing, setImporting] = useState(false);
  const [pdkStep, setPdkStep] = useState<Json>(null);       // the PDK read with the last cell import (backend bridge_read.pdk_with_import)
  const declaredHere = !!circuit?.loaded && !!circuit.native_draft && circuit.circuit?.library === ref.library && circuit.circuit?.cell === ref.cell
    && !!circuit.working_copy?.verified;
  const importCell = async () => {
    const declare = !declaredHere;
    // Asked in the window that was clicked (the Virtuoso window): the main window's dialog opened behind it.
    if (declare && !(popup ?? window).confirm(copyQuestion(ref))) return;
    setImporting(true); setNativeError(null);
    try {
      const answer = await api.nativeImport(profileId!, ref.library, ref.cell, ref.testbench_cell ?? null, declare);
      if (answer?.pdk?.state === 'read') pdksChanged();  // the Components list in the RL network block shows it at once
      // The selects are locked while a cell is read; should the page follow another cell anyway, its own load shows it. A
      // registered task chosen meanwhile keeps the last cell's fields: the draft's load outbid the task's, and could
      // exchange its Probes (review of 2026-10-01).
      const now = latest.current.circuit;
      if (now.source !== ref.source || (now.task_id ?? null) !== (ref.task_id ?? null) || now.library !== ref.library
        || now.cell !== ref.cell || (now.testbench_cell ?? null) !== (ref.testbench_cell ?? null)) return;
      setPdkStep(answer?.pdk ?? null);                    // the cell's PDK, read in the same press (2026-09-27); an older server sends none
      await load(ref, 'press');
    }
    catch (e: any) { nativeProblem(e); }
    finally { setImporting(false); }
  };
  useEffect(() => { setPdkStep(null); }, [loadKey]);       // the line is about the cell it was read with

  // Probes follow the testbench (user request 2026-09-21): a cell read THROUGH a testbench brings, in Probes, the results
  // of the circuit type that testbench fits, each naming the testbench net or supply branch it is read from
  // (profiles.testbench_probes - from the export that was read, not from what the box shows now). Only after a choice of
  // library / cell / testbench or a press of Read, never on page load; and only over rows that are nobody's work - empty,
  // brought by an earlier testbench, or still exactly the rows the last registered task brought. That task's untouched
  // targets leave Specs with them (they point at its probes). Rows someone edited stay, and the line offers the exchange.
  // A choice exchanges within its own Undo step; a press is a step of its own. (The circuit type a saved task measures
  // with is read from its Probes when it is saved.)
  const [probeNote, setProbeNote] = useState<Json>(null);  // { state: brought | kept | none, found, clearedTask? }
  const brought = useRef<string[]>([]);                     // Probes this panel brought from a testbench (JSON), this page session
  const followCount = useRef(0);
  const followTestbench = async (loaded: Json, press: boolean) => {
    const mine = ++followCount.current;
    const found = loaded?.loaded && loaded.native_draft && !loaded.profile_task ? loaded.testbench_probes : null;
    if (!found) { setProbeNote(null); return; }
    if (!found.rows.length) { setProbeNote({ state: 'none', found }); return; }
    if (sameJson(latest.current.measurements, found.rows)) { setProbeNote(null); return; }
    const taskId = latest.current.circuit.task_id;
    const starter = taskId ? await api.starter(taskId).catch(() => null) : null;
    if (mine !== followCount.current) return;
    const now = latest.current;
    const untouched = !(now.measurements ?? []).length || brought.current.includes(JSON.stringify(now.measurements))
      || (!!starter && sameJson(tablesOf(now).measurements, tablesOf(starter).measurements));
    if (!untouched) { setProbeNote({ state: 'kept', found }); return; }
    const staleTargets = !!starter && (now.targets ?? []).length > 0 && sameJson(tablesOf(now).targets, tablesOf(starter).targets);
    brought.current.push(JSON.stringify(found.rows));
    setConfig(c => ({ ...c, measurements: found.rows, ...(staleTargets ? { targets: [] } : {}) }), press);
    setProbeNote({ state: 'brought', found, clearedTask: staleTargets ? taskId : null });
  };
  const takeTestbenchProbes = () => {
    const found = probeNote.found;
    brought.current.push(JSON.stringify(found.rows));
    setConfig(c => ({ ...c, measurements: found.rows }));
    setProbeNote({ state: 'brought', found });
  };
  const noteHere = probeNote && probeNote.found.library === ref.library && probeNote.found.cell === ref.cell ? probeNote : null;
  const namedHere = namedTestbench(cells, chosen.cell);
  const cellInfo = new Map<string, Json>((cells?.cells ?? []).map((c: Json) => [c.name, c]));   // one look-up per option, not a search

  // Keep the current task and its rows together until the next task is ready. A switch is one Undo step, after any
  // edited rows have been explicitly discarded. Project identity stays; the run label follows the selected task.
  const [taskRows, setTaskRows] = useState<Json>(null);
  const [taskLoading, setTaskLoading] = useState<string | null>(null);
  const [taskLoadError, setTaskLoadError] = useState<string | null>(null);
  const following = useRef(0);
  useEffect(() => () => { following.current++; }, []);
  const starterProblem = (e: any, taskId: string) => (e.status === 404 && taskId.startsWith('real:')
    ? 'This backend is older than the page and has no starting rows for a real task yet: restart it (gator_workbench.cli serve).' : e.message);
  const goneMock = (taskId?: string | null) => !!taskId && taskId.startsWith('synthetic:') && tasks.length > 0 && !tasks.some(t => t.task_key === taskId);
  const removedMock = ref.source === 'registered_task' && goneMock(ref.task_id);
  // `labels`: the class and PDK id of a task just saved (the ngspice window) - not in the task list read before the save.
  const chooseTask = async (taskId: string, labels?: { circuit_class?: string | null; pdk_id?: string | null }, reload = false) => {
    const before = latest.current, mine = ++following.current;
    const currentTask = before.circuit.source === 'registered_task' ? before.circuit.task_id : null;
    const stillHere = () => mine === following.current && latest.current.circuit === before.circuit;
    const brought = taskRows?.task === currentTask ? taskRows.starter : null;
    setTaskLoadError(null);
    setTaskLoading(taskId);
    try {
      const [previous, starter] = await Promise.all([
        currentTask && currentTask !== taskId ? api.starter(currentTask).catch(() => null) : null,
        api.starter(taskId)]);
      if (!stillHere()) return;
      // Check the rows NOW: the user can edit while the read is in flight. A saved-again task may differ from the
      // rows it originally brought; either known baseline counts as untouched when switching to another task.
      const now = latest.current, baseline = currentTask === taskId ? starter : previous;
      const untouched = noRows(now) || sameRows(now, starter) || (!!baseline && sameRows(now, baseline))
        || (!reload && !!brought && sameRows(now, brought));
      if (!untouched && !window.confirm(`${reload ? 'Reload saved values' : `Switch to ${taskId}`}?\n\n`
        + 'This replaces your unsaved Parameters, Probes and Specs edits.\n'
        + 'OK = discard those edits and load the saved rows.\nCancel = keep the current task and edits. You can save them with Save task first.')) return;
      const nextCircuit = { ...starter.circuit, ...labels, source: 'registered_task', task_id: taskId };
      setConfig(c => c.circuit !== before.circuit ? c : ({ ...c,
        circuit: nextCircuit,
        project: { ...c.project, task_name: starter.project.task_name },
        parameters: starter.parameters, targets: starter.targets, measurements: starter.measurements }));
      noteRowsFrom(taskId, starter.revision);    // which saved revision these rows are (record 7.203)
      request.current++;                         // any pending circuit view still belongs to the previous task
      followCount.current++;                     // a pending Virtuoso probe read cannot replace the new task's rows
      setCircuit(null);
      if (currentTask === taskId) load(nextCircuit);
      setTaskRows({ task: taskId, state: 'brought', starter });
    } catch (e: any) {
      if (stillHere()) setTaskLoadError(`Could not load ${taskId}. The current task and rows are unchanged. ${starterProblem(e, taskId)}`);
    } finally {
      if (mine === following.current) setTaskLoading(null);
    }
  };
  // A cell that already has a registered task - the task saved from it, or one of the verified built-in circuits - gets
  // no second task: the note names the task. One short button, because it is about THIS cell (not a list of tasks); it
  // does what choosing the task in the Project column does.
  const builtIn = circuit?.profile_task_generated === false;
  const taskNote = circuit?.profile_task && virtuosoOn ? (
    <div className="note">
      <p><b>This cell already has a registered task:</b> <code>{circuit.profile_task}</code>{builtIn ? ' (a verified built-in circuit)' : ''}{' '}
        Choose it under <b>Task</b> in the Project column.</p>
      <details className="more"><summary>What this means</summary>
        <p>The workbench can already optimize this cell - through that task, in the Project column.{builtIn ? ' A verified built-in circuit gets no second task.'
          : ' Open it to change it (Save task). Another task needs another copy of the cell: make one in Virtuoso and read it here. To start over from this cell, open the task and press Delete task.'}</p></details>
    </div>) : null;
  // What was read straight from Virtuoso. It is a line of the Hierarchy block; while no circuit is loaded (browse only)
  // there is no such block and it stands alone at the end of the window.
  const nativeSchematic = <NativeSchematic native={native} open={nativeOpen} setOpen={setNativeOpen} />;
  const circuitInfo = <CircuitDetails circuit={circuit} open={hierarchyOpen} setOpen={setHierarchyOpen}>
    {virtuosoOn && nativeSchematic}</CircuitDetails>;
  const readable = !!profileId && !!chosenCell?.has_schematic && !importing && !listing;
  // The warning stays in view (never folded): the confirm repeats it once, when Read is pressed.
  const copyWarning = (
    <p className="warn copy-warning"><b>Work on a copy, never on your design.</b> The workbench makes no copy of its own: saving a task writes the
      Maestro test into the testbench, and every run sets device sizes in the cell (put back when the run ends). Copy the cell and its testbench
      in Virtuoso first, choose the copy above, and confirm when Read asks.</p>);

  // ---- the left column: the project and the registered task --------------------------------------------------------------
  const column = (
    <section className="panel">
      {/* No Project name box (record 7.159, user: "remove the project name box in the Project module"): the name only filed
          the last run, which the RL model's own label in Run configuration does now. */}
      <h3>Registered task</h3>
      {!offered && <div className="note"><p>This configuration was saved with a Spectre netlist file{ref.netlist_path ? <> (<code>{ref.netlist_path}</code>)</> : null}.
        The workbench no longer imports netlists: choose a task below, or a Virtuoso cell in its window.</p></div>}
      {/* The task the page follows, as plain text, and ONE button "Tasks..." that opens the task window (user request
          2026-10-06, record 7.227): it replaced the drop-down list of tasks, as "Runs..." replaced the list of runs. The
          text says what the list's placeholder used to: no task, a Virtuoso cell, a removed task. A choice in the
          window is the old list's choice: chooseTask. */}
      <div className="row task-row" title="The circuit the editors and a run are about. A cell read from Virtuoso becomes one of these with Save task.">
        <span className="task-caption">Task</span>
        <TaskListButton tasks={tasks} runs={runs} ngspiceOffered={showNgspice} loading={taskLoading} onChoose={key => chooseTask(key)}
          onRefresh={() => api.tasks().then(t => { setTasks(t.tasks); return t.tasks; })} onRefreshRuns={refreshRuns}
          current={ref.source === 'registered_task' && ref.task_id && !removedMock ? ref.task_id : null}
          currentMark={ref.source === 'registered_task' && ref.task_id && !removedMock ? taskMark(tasks.find(t => t.task_key === ref.task_id) ?? { kind: 'real', available: true }, showNgspice) : undefined}
          currentText={ref.source !== 'registered_task' ? (virtuosoOn ? (ref.cell ? `(none: ${ref.library}/${ref.cell} is read from Virtuoso)` : '(none: a Virtuoso cell is being chosen)')
            : '(none: the saved source was removed)') : !ref.task_id ? '(choose a task)' : `${ref.task_id} (removed)`} />
      </div>
      {ref.source === 'registered_task' && (<>
        {/* A configuration saved with a removed MOCK task (the four of status record 7.59; the last one, synthetic:gpdk045_ota5,
            on 2026-09-30, record 7.128): a plain note, not a red "Blocked". */}
        {removedMock && <div className="note"><p><code>{ref.task_id}</code> no longer exists: the workbench has no MOCK task since
          2026-09-30. Choose one of your saved tasks under Task; it brings its own rows.</p></div>}
        {/* Choosing a task loads its rows. Reload is only for resetting the current task to its saved values. */}
        {ref.task_id && !removedMock && <div className="row task-buttons">
          <button disabled={!!taskLoading} onClick={() => chooseTask(ref.task_id, undefined, true)} title="Reload saved values: Reset Parameters, Probes and Specs to the saved task. Asks before discarding edits. Project, run and output settings stay. Undo takes it back."><Icon name="load" label="Reload saved values" /></button>
          <span className="spacer" />
          {(deletableName || ngspiceTask) && <button disabled={!!profileBusy} onClick={ngspiceTask ? deleteNgspice : deleteProfile}
            title={ngspiceTask ? 'Delete task: Asks once more. The task leaves the Registered task list; its deck and task file are kept aside on the backend machine, and runs already made keep their data.'
              : 'Delete task: Asks once more. The task leaves the Registered task list and its cell can get a new one; its files are kept aside on the backend machine, and runs already made keep their data.'}>
            <Icon name="delete-task" label={profileBusy === 'delete' ? 'Deleting...' : 'Delete task'} /></button>}
        </div>}
        {profileMessage?.what === 'delete' && <p className={profileMessage.level === 'ok' ? 'ok' : 'error'}>{profileMessage.text}</p>}
        {!taskLoading && taskRows?.task === ref.task_id && sameRows(config, taskRows.starter) && <p className="hint task-rows">Parameters, Probes and Specs now show this task's rows
              {taskRows.starter.targets.length ? '' : ' - it has no targets of record, so Specs is yours to fill (its results are ready in Probes)'}. Undo brings the previous ones back.</p>}
      </>)}
      {taskLoading && <p className="hint task-rows" role="status">Loading <code>{taskLoading}</code>...</p>}
      {taskLoadError && <p className="error task-rows" role="alert">{taskLoadError}</p>}
      {/* The two other ways to a task, each ONE button that opens its window (user request 2026-09-23): the Virtuoso cellview
          import and an ngspice netlist. One small grid, so the two buttons stand under each other in one column and the text
          beside each says what the page follows (user: "arrange this part to make it more readable", 2026-09-23). */}
      <div className="launchers">
        {showVirtuoso && <div className="row virtuoso-launcher">
          <span className="hint">{virtuosoOn && ref.cell ? <>Read from Virtuoso: <code>{ref.library}/{ref.cell}</code></> : virtuosoOn ? 'Reading from Virtuoso: choose a cell in the window'
            : 'From a cell you copied in Virtuoso:'}</span>
          <button className="virtuoso-button" onClick={openWindow} title={popup ? 'The Virtuoso window is open: press to bring it to the front.'
            : 'Opens the Virtuoso window: choose a library, a cell and its testbench, read the cell into the workbench (it asks whether the cell is a copy you made), set it up, save it as a task. Opening it lists the libraries of that Virtuoso - and, for the cell chosen last time, its cells and schematic - read-only; nothing comes into the workbench until you press Read.'}>Virtuoso cell...</button>
        </div>}
        {showVirtuoso && blocked && <p className="error">{BLOCKED}</p>}
        {showNgspice && <div className="row virtuoso-launcher ngspice-launcher">
          <span className="hint">{ngspiceTask ? <>ngspice task: <code>{ngspiceTask}</code></> : 'From an ngspice netlist (a SPICE deck):'}</span>
          <NgspiceButton config={config} circuit={circuit} chooseTask={chooseTask} onTasksChanged={refreshTasks} />
        </div>}
      </div>
      {deletedHere && !circuit?.profile_task && (<>
        <p className="ok">Task <code>{deletedHere.deleted}</code> deleted. Its cell <code>{deletedHere.library}/{deletedHere.cell}</code> can get a new one (Virtuoso cell...).</p>
        <details className="more hint"><summary>Where its files went</summary>
          <p>Nothing was erased. They are kept on the backend machine in <code>{deletedHere.kept_copy}</code>.</p></details>
      </>)}
      {/* The labels of the circuit, saved with every run: one folded line whose text names them. */}
      <details className="more hint labels"><summary>Labels: class <b>{ref.circuit_class ?? 'unspecified'}</b>, PDK <b>{ref.pdk_id ?? 'unspecified'}</b>{ref.dut_hierarchy ? <>, DUT <b>{ref.dut_hierarchy}</b></> : null}</summary>
        <label title="A DUT may be identified inside one testbench; separate DUT/testbench files are not required.">DUT hierarchy / subcircuit<input value={ref.dut_hierarchy ?? ''} onChange={e => patch({ dut_hierarchy: e.target.value || null })} /></label>
        <div className="row">
          <label title="What kind of circuit this is: opamp, ldo, vco, ... A label for your records. Results tables are grouped by it, and the validator uses it to check a claim such as 'tested on an unseen circuit class'.">Circuit class
            <Typed list="circuit-classes" value={ref.circuit_class} format={v => v ?? ''} parse={t => ({ value: t || 'unspecified' })} onChange={v => patch({ circuit_class: v })} />
            <datalist id="circuit-classes">{['opamp', 'ldo', 'vco', 'bandgap', 'comparator', 'oscillator', 'unspecified'].map(c => <option key={c} value={c} />)}</datalist></label>
          <label title="Which process design kit (technology) the circuit is built in, e.g. gpdk045. Written into the run records so a result can be traced to its technology. PDK files are never copied.">PDK id
            <Typed value={ref.pdk_id} format={v => v ?? ''} parse={t => ({ value: t || 'unspecified' })} onChange={v => patch({ pdk_id: v })} /></label>
        </div>
        <p>Circuit class and PDK id are labels saved with every run. They do not change the simulation or the optimization;
          "unspecified" is fine for a single run. A task brings its own; a cell read from Virtuoso brings the PDK id of its library's technology library.</p>
      </details>
      {error && <p className="error">{error}</p>}
      {ref.source === 'registered_task' && circuit && !circuit.loaded && !removedMock && <div className="blocker"><b>Blocked:</b> {circuit.blocker}
        {circuit.interface_contract && <details><summary>Interface contract</summary><pre>{JSON.stringify(circuit.interface_contract, null, 1)}</pre></details>}</div>}
      {ref.source === 'registered_task' && circuit?.loaded && (<>
        {circuit.mock && <p className="mock">MOCK evaluation backend: {circuit.evaluation_backend}</p>}
        {circuit.simulator === 'ngspice' && (<>
          <p className="real">ngspice evaluation backend: every evaluation is one real circuit simulation by ngspice (no license). Start asks you to
            confirm the number of simulations first.</p>
          {circuit.circuit?.connection_problem && <p className="warn">{circuit.circuit.connection_problem}</p>}
          <div className="note">
            <p><b>ngspice netlist task</b>, revision {circuit.circuit?.revision ?? '?'}{circuit.circuit?.title ? <>: <i>{circuit.circuit.title}</i></> : null}.
              {' '}{(circuit.circuit?.measurements ?? []).length} results: <code>{(circuit.circuit?.measurements ?? []).join(', ')}</code>.</p>
            <details className="more"><summary>How it runs</summary>
              <p>Each evaluation writes the chosen sizes into their own places in the deck, runs <code>ngspice -b</code> on it through the ngspice
                connection (on this machine, or over SSH with the deck sent in), and reads the <code>name = value</code> lines it prints. To change
                the deck, press <b>ngspice netlist...</b> above (shown while an ngspice connection is in use): saving stores the next revision
                (runs made before keep their own copy).</p></details>
          </div>
        </>)}
        {/* Until the task has its reference. A finished Baseline simulation records it by itself (status record 7.78);
            one whose measurement was refused is named with the reason, instead of the same standing advice. The standing advice is
            one line since record 7.188 (design advice: shorter notes), its explanation in the tooltip. */}
        {circuit.generated_profile && !circuit.baseline_recorded && (circuit.baseline_attempt
          ? <p className="warn">The Baseline simulation <code>{String(circuit.baseline_attempt.run_id ?? '').slice(0, 12)}</code>
              {circuit.baseline_attempt.ended_utc ? ` (${String(circuit.baseline_attempt.ended_utc).slice(0, 16).replace('T', ' ')} UTC)` : ''} gave no usable
              baseline: {circuit.baseline_attempt.reason} Run <b>Baseline simulation</b> again once that is put right; a finished one becomes
              the task's reference by itself.</p>
          : <p className="warn" title={'Baseline simulation is one real Spectre run: the starting design, then 64 random designs for the calibration; '
              + "it asks for your budget first. Its first simulation becomes the task's reference by itself, before any optimization run."}>No real baseline
              yet: run <b>Baseline simulation</b> first.</p>)}
        {saved && saved.task_key === ref.task_id && <p className="ok">Saved the new task <code>{saved.task_key}</code>. It runs in
          <code> {saved.copy?.library}/{saved.copy?.testbench}</code>{saved.copy?.library === saved.original?.library ? ' - the cell you declared as your copy' : ' - its working copy'}; nothing has been simulated yet.</p>}
        {/* The circuit picture (record 7.158) above the long note, so it is in view while Parameters rows are pointed at. */}
        <CircuitPicture circuit={circuit} />
        {generatedName && (
          <div className="note">
            <TaskSave profileId={profileId} library={null} cell={null} task={generatedName}
              revision={tasks.find(t => t.task_key === ref.task_id)?.revision ?? null} hasCopy
              config={config} setConfig={setConfig} onSaved={taskSaved} onSavedElsewhere={savedElsewhere}
              onReload={() => chooseTask(ref.task_id, undefined, true)} bar={taskSlot} notes={taskNotes} />
            {/* One line; the explanation is its tooltip (record 7.177, user: "reduce the texts this part"). */}
            <p title={'Start, Baseline simulation and Resume first check that the editors, this saved task and its cell in Virtuoso agree. '
              + 'The check simulates nothing; a difference starts nothing and says what to do.'}><b>Before every run:</b> the editors, the task and its cell must agree.</p>
            <details className="more"><summary>What the check compares</summary>
              <ul className="steps-list">
                <li>The rows of Parameters, Probes and Specs against the saved task. While you edit, the header's blocking issues say it too.</li>
                <li>The cell in Virtuoso against the task: the run adapter connects (no ADE/Maestro window may be open on the copy), Virtuoso exports
                  its netlist, the export is compared with the saved one - topology and every parameter - and the simulation deck is written.</li>
                <li>For a task measured by Maestro: the cell's Maestro test against the task.</li>
              </ul>
              <p>Everything but the rows needs the link up. Nothing is written into Virtuoso.</p></details>
            <div className="row">
              <button disabled={!!profileBusy} onClick={checkTask} title="The check Start runs by itself before every run. Read-only, no simulation.">
                {profileBusy === 'check' ? 'Checking...' : 'Check now'}</button>
            </div>
            {taskCheck && <CheckSteps result={taskCheck} />}
            {profileMessage && profileMessage.what !== 'delete' && <p className={profileMessage.level === 'ok' ? 'ok' : 'error'}>{profileMessage.text}</p>}
          </div>)}
        {circuitInfo}
      </>)}
    </section>);

  // ---- the Virtuoso window: library / cell / testbench, the read, the setup, the first save --------------------------------
  const view = (
    <div className="virtuoso-window">
      <h2>Virtuoso cell</h2>
      <p className="hint">Read a cell from Virtuoso into the workbench, set it up and save it as a task. Choosing lists what Virtuoso has (read-only,
        no simulation); nothing is read on its own.</p>
      {!profileId && <p className="warn">Press "Connection" in the workbench and choose a Virtuoso connection: the libraries are read from that Virtuoso.</p>}
      {!virtuosoOn && offered && <p className="hint follows-task">The workbench follows the task <code>{ref.task_id}</code> now. Choosing a library here makes it follow the
        cell instead; the task is one choice away in the Project column.</p>}
      <label>Library
        <select value={chosen.library ?? ''} disabled={!libraries || importing} onChange={e => patch({ source: 'virtuoso', library: e.target.value || null, cell: null, view: null, testbench_cell: null }, 'choice')}>
          <option value="">{listing === 'libraries' ? 'Reading the libraries...' : libraries ? `(choose one of ${libraries.length})` : '(not listed)'}</option>
          {withCurrent(libraries ?? [], chosen.library).map(l => <option key={l} value={l}>{l}</option>)}
        </select>
      </label>
      <label title="Only a cell with a schematic view can be read.">Cell
        {/* A new cell takes its own tb_<cell>; without one, a testbench chosen by hand stays and the old cell's tb_ goes. */}
        <select value={chosen.cell ?? ''} disabled={!cells || importing} onChange={e => {
          const cell = e.target.value || null;
          patch({ source: 'virtuoso', cell, view: cell ? 'schematic' : null,
            testbench_cell: namedTestbench(cells, cell) ?? (chosen.testbench_cell === namedHere ? null : chosen.testbench_cell ?? null) }, 'choice');
        }}>
          <option value="">{!chosen.library ? '(choose a library first)' : listing === 'cells' ? 'Reading the cells...' : cells ? `(choose one of ${cells.cells.length})` : '(not listed)'}</option>
          {withCurrent((cells?.cells ?? []).map((c: Json) => c.name), chosen.cell).map(name => {
            const readableCell = !cells || cellInfo.get(name)?.has_schematic !== false;
            return <option key={name} value={name} disabled={!readableCell}>{name}{readableCell ? '' : '  (no schematic view)'}</option>;
          })}
        </select>
      </label>
      {chosenCell && <details className="more hint"><summary>View: <b>schematic</b></summary>
        <p>The only view the reader opens, so there is nothing to choose.
          {chosenCell.views.length > 1 && ` This cell also has: ${chosenCell.views.filter((v: string) => v !== 'schematic').join(', ')}.`}</p></details>}
      <label title="The cell that holds the test setup around the design (supply, stimulus, load). A task simulates it and keeps its Maestro test there, and Probes are read from it. A cell named tb_ + the cell's name is chosen by itself.">Testbench cell
        <select value={chosen.testbench_cell ?? ''} disabled={!cells || importing} onChange={e => patch({ source: 'virtuoso', testbench_cell: e.target.value || null }, 'choice')}>
          <option value="">(none)</option>
          {withCurrent((cells?.cells ?? []).filter((c: Json) => c.has_schematic).map((c: Json) => c.name), chosen.testbench_cell).map(name => <option key={name} value={name}>{name}</option>)}
        </select>
      </label>
      {namedHere && chosen.testbench_cell === namedHere && <p className="hint tb-named">Found by its name: <code>tb_</code> + the cell's name.</p>}
      <div className="row">
        <button disabled={!profileId || !!listing} onClick={() => setRefresh(n => n + 1)} title="Reads the libraries, the cells and the schematic again, e.g. after the link came up or the design changed in Virtuoso. Read-only and zero-cost.">Refresh</button>
        {listing && <span className="hint">Reading the {listing} from Virtuoso...</span>}
        <PdkWindowButton profileId={profileId} circuitPdk={ref.pdk_id} />
      </div>
      {pdkStep && <p className={`pdk-step ${pdkStep.state === 'read' ? 'hint' : 'warn'}`}>{pdkStep.state === 'read'
        ? <>PDK <b>{pdkStep.pdk_id}</b> read with the cell: {pdkStep.summary?.devices} components (version {String(pdkStep.sha256 ?? '').slice(0, 8)}){pdkStep.ideal_parts?.summary
            ? ` and ${pdkStep.ideal_parts.summary.recognized} ideal parts of ${pdkStep.ideal_parts.library}` : pdkStep.ideal_parts?.error ? `; the ideal parts of ${pdkStep.ideal_parts.library} were not read (${pdkStep.ideal_parts.error})` : ''}. To build the network with it, choose it under Components in the RL network block.</>
        : pdkStep.state === 'not_read' ? <>The cell was read; its PDK <b>{pdkStep.technology_library}</b> was not: {pdkStep.reason} "PDK window..." reads it by name.</>
        : <>No PDK read with the cell: {pdkStep.reason}</>}</p>}
      {cells?.truncated && <p className="hint">Only the first {cells.cells.length} cells are listed.</p>}
      {nativeError && <p className="error">{nativeError}</p>}
      {virtuosoOn && error && <p className="error">{error}</p>}
      {circuit && taskNote}
      {virtuosoOn && circuit && !circuit.loaded && !taskNote && (
        // Not a fault and nothing to fix in this form: said in plain words. No list of the circuits that already have a
        // task here (user, 2026-09-22): whoever wants one of those picks it in the Project column.
        <div className="note">
          <p><b>Browse only: you can look at this cell here, but the workbench cannot optimize it yet.</b></p>
          <details className="more"><summary>Why: it has no <i>circuit profile</i> yet</summary>
            <p>To optimize a circuit in the real Virtuoso, the workbench needs a circuit profile - a checked description of three things:</p>
            <ul className="steps-list">
              <li>which device sizes it may change, within which limits and in which steps (Virtuoso rounds what is typed, so this is tested for each circuit);</li>
              <li>which testbench simulates the circuit, and under which conditions;</li>
              <li>how the results - gain, frequency, current ... - are read from the simulation.</li>
            </ul>
            <p>Circuits that already have one are under Registered task, in the Project column.</p>
          </details>
          {copyWarning}
          <p><b>To start a profile for this cell</b>, read it into the workbench
            {chosen.testbench_cell ? <> through the testbench <code>{chosen.testbench_cell}</code>.</> : <> (choose its <b>Testbench cell</b> above first, if it has one).</>}</p>
          <details className="more"><summary>What reading the cell does</summary>
            <p>Virtuoso exports the netlist and the device sizes are read. Read-only, no simulation, some seconds. Reading asks once whether
              the cell is a copy you made; "OK" makes it the cell the task flow works in.</p></details>
          <div className="row"><button className="primary" disabled={!readable} onClick={importCell}>
            {importing ? 'Reading the cell from Virtuoso...' : 'Read this cell into the workbench'}</button></div>
          <details><summary>Technical details</summary><p>{circuit.blocker}</p>
            {circuit.interface_contract && <pre>{JSON.stringify(circuit.interface_contract, null, 1)}</pre>}</details>
        </div>)}
      {virtuosoOn && circuit?.loaded && circuit.native_draft && !taskNote && (
        <div className="note">
          <p><b>Read from Virtuoso. Not optimizable yet: it has no circuit profile.</b></p>
          <details className="more"><summary>What you can do with it now</summary>
            <p>The workbench holds the export of this cell, so you can look at it and fill the three editors. Start stays disabled.</p>
            <p>Next: fill Parameters, Probes and Specs - <b>Read setup</b> below takes the outputs and specs of the cell's Maestro test - then press
              <b> Save task</b>: it writes the rows into this cell's Maestro view (the copy you declared) and reads it back. Claude Code or Codex
              (Agent tab) can help with any of it, from what you describe.</p>
          </details>
          {(circuit.circuit?.testbench_cell ?? null) !== (ref.testbench_cell ?? null) && (
            <p className="warn tb-stale">This cell was read {circuit.circuit?.testbench_cell ? <>through <code>{circuit.circuit.testbench_cell}</code></> : 'without a testbench'}.
              Press <b>Read the cell again</b> to read it {ref.testbench_cell ? <>through <code>{ref.testbench_cell}</code></> : 'without one'}: Probes then follow it.</p>)}
          {!circuit.working_copy?.verified && copyWarning}
          <div className="row">
            <button disabled={!readable} onClick={importCell} title="After a change in Virtuoso, or to export through another testbench cell. Read-only.">{importing ? 'Reading...' : 'Read the cell again'}</button>
          </div>
          <WorkingCopy profileId={profileId} library={ref.library} cell={ref.cell} record={circuit.working_copy} config={config} setConfig={setConfig} />
          {noteHere?.state === 'brought' && (() => {
            const rows: Json[] = noteHere.found.rows, supply = rows.find(r => /:p$/.test(r.signal ?? ''))?.signal, net = rows.find(r => r.signal && !/[:\s]/.test(r.signal))?.signal;
            return <>
              <p className="hint tb-probes">Probes now show what the testbench <code>{noteHere.found.testbench_cell}</code> measures: {rows.length} results of the
                circuit type <b>{noteHere.found.circuit_type_label}</b>.{noteHere.clearedTask && <> The targets of <code>{noteHere.clearedTask}</code> were removed from
                Specs: they belonged to that task.</>} Undo brings the previous rows back.</p>
              <details className="more hint"><summary>What the Probes rows say</summary>
                <p>Each row is a result the circuit type computes from the simulation. Its <i>signal</i> says where in this testbench it is read
                  {net && <>: a net such as <code>{net}</code></>}{supply && <>, or <code>{supply}</code>, the current through the supply
                  source <code>{supply.slice(0, -2)}</code></>}. The circuit type decides how a result is measured, so changing <i>signal</i> does
                  not move it. Targets on these results go in Specs.</p></details>
            </>;
          })()}
          {noteHere?.state === 'kept' && <div className="row tb-probes"><span className="warn">Probes hold rows you edited, not the ones of the
            testbench <code>{noteHere.found.testbench_cell}</code>.</span>
            <button onClick={takeTestbenchProbes} title="Replaces the rows of Probes with the results this testbench gives. Undo takes it back.">Use testbench probes</button></div>}
          {noteHere?.state === 'none' && (<>
            <p className="hint tb-probes">Probes were left as they were. {noteHere.found.reason}</p>
            {Object.keys(noteHere.found.not_fitting ?? {}).length > 0 && <details className="more hint"><summary>Why no circuit type fits</summary>
              <ul className="steps-list">{Object.entries(noteHere.found.not_fitting).map(([type, why]: [string, any]) => <li key={type}><b>{type}</b>: {why}</li>)}</ul></details>}
          </>)}
          {/* The save itself sits at the right end of the editors' tab line (TaskSave portals, user request 2026-09-22). */}
          <p><b>Then save it as a task:</b> <b>Save task</b> is above the editors in the workbench, next to their tabs.</p>
          <details className="more hint"><summary>What Save task does</summary>
            <p>It checks the rows, makes this cell's Maestro test say what the task says (its outputs, specs and analyses, read back afterwards),
              reads the cell into the workbench again and stores the task file with the task's files next to it. No simulation. Saving again
              makes the next revision of the same task; the recorded baseline is kept only if what is measured did not change. Another task
              needs another copy of the cell: make one in Virtuoso and read it here.</p></details>
        </div>)}
      {virtuosoOn && circuit?.loaded && circuitInfo}
      {!(virtuosoOn && circuit?.loaded) && nativeSchematic}
    </div>);
  // The first save of a cell read from Virtuoso. It lives with the column, not in the Virtuoso window: its buttons sit on
  // the editors' tab line and hold what waits for the save (task-file parts applied) - closing the window took that away
  // (audit 2026-09-30).
  const firstSave = virtuosoOn && circuit?.loaded && circuit.native_draft && !taskNote && (
    <TaskSave profileId={profileId} library={ref.library} cell={ref.cell} task={null} hasCopy={!!circuit.working_copy?.verified}
      config={config} setConfig={setConfig} onSaved={taskSaved} onSavedElsewhere={savedElsewhere} bar={taskSlot} notes={taskNotes} />);
  const titleFacts = titleSlot && createPortal(<TitleFacts config={config}
    revision={ref.source === 'registered_task' ? tasks.find(t => t.task_key === ref.task_id)?.revision ?? null : null} />, titleSlot);
  return <>{column}{firstSave}{titleFacts}{popup && root && createPortal(view, root)}</>;
}
