import { CircuitDetails, NativeSchematic, type SizeAdding, sizesAddable, useVirtuosoBrowser } from './CircuitBrowser';
import { memo, MutableRefObject, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, Json } from '../api';
import { plural } from '../format';
import { kindUnit } from '../units';
import { newRow } from './editorRules';
import { tasksShared } from '../shared';
import { usePopupWindow } from './popupWindow';
import { Blocked, PopupPortal } from './popupParts';
import { VIRTUOSO_WINDOW } from '../contract';
import { pdksChanged } from './Pdk';
import { NgspiceButton } from './Ngspice';
import { TaskBaseline } from './TaskBaseline';
import { TaskSave, baselineText } from './TaskSave';
import { shownName, TaskListButton, taskMark } from './TaskList';
import { CheckSteps } from './Consistency';
import { Typed } from './Typed';
import { CircuitPicture } from './CircuitPicture';
import { useNewest } from '../newest';
import { sameRows } from './taskRows';
import { useTaskActions } from './taskActions';
import { useTestbenchProbes } from './testbenchProbes';
import { RELOAD_SAVED_REQUEST, type TaskLoad, useTaskChoice } from './taskChoice';
import { openConnection, openTasksAt } from '../openAt';
import { NO_TESTBENCH, VirtuosoWindow } from './VirtuosoWindow';

/** The connection block lives in Connection.tsx: one button in this column that opens the connection window. */

/** The circuit panel: the task the page follows and the circuit it is about. Since record 7.362 (the user's Option D) it draws
 *  the task into the editors - its name and revision at the start of their tab line, Check now at its end, its own lines under
 *  the toolbar - and keeps the circuit alone in its column (labels, picture, notes, hierarchy), folded away until "Show
 *  circuit". Reading a cell from Virtuoso - library / cell / testbench, the read, the task's first save - lives in a window
 *  of its own (the mechanism of the connection window: a portal into a named pop-up), opened by "New task: From a Virtuoso
 *  cell..." in the Tasks window. An ngspice netlist (a SPICE deck pasted or loaded from a file) becomes a task the same way,
 *  behind "From an ngspice netlist..." (Ngspice.tsx): such a task runs on an ngspice connection and needs no Virtuoso.
 *  The workbench makes no working copy of its own any more: reading a cell asks whether it is a copy the user made, and
 *  then works in THAT cell (the backend records it as the cell's working copy: import with `work_here`). */

/** The circuit sources: a registered task (the column) and a Virtuoso cell (the window). "Import Spectre netlist" was
 *  removed (user request, status record 7.53): a configuration saved before still names `netlist`; the column then says so. */
const SOURCES = ['registered_task', 'virtuoso'];

const CIRCUIT_CLASSES = ['opamp', 'ldo', 'vco', 'bandgap', 'comparator', 'oscillator', 'unspecified'];
/** What the two ways to a new task open (their buttons: the Tasks window's "New task", and the tab line while the page follows one). */
const VIRTUOSO_OPENS = 'Opens the Virtuoso window: choose a library, a cell and its testbench, read the cell into the workbench (it asks whether the cell is a copy you made), set it up, save it as a task. Opening it lists the libraries of that Virtuoso - and, for the cell chosen last time, its cells and schematic - read-only; nothing comes into the workbench until you press Read.';
const NGSPICE_OPENS = 'Opens the ngspice window: paste or load a SPICE deck, check it and save it as a task that runs on an ngspice connection. Opening it runs nothing.';
/** Check now's tooltip: the sentence and the steps the task's block showed until record 7.362 (records 7.177, 7.362). */
const CHECK_NOW = 'Check now: Start, Calibration and Resume first check that the editors, this saved task and its cell in Virtuoso agree - the check '
  + 'simulates nothing; a difference starts nothing and says what to do. It compares the rows of Parameters, Probes and Specs with the saved task '
  + "(while you edit, the header's blocking issues say it too); the cell in Virtuoso with the task - the run adapter connects (no ADE/Maestro window "
  + 'may be open on the copy), Virtuoso exports its netlist, the export is compared with the saved one, topology and every parameter, and the '
  + "simulation deck is written; and, for a task measured by Maestro, the cell's Maestro test with the task. Everything but the rows needs the "
  + 'link up. Nothing is written into Virtuoso.';
/** Use the page's themed dropdown; its Custom option keeps arbitrary research labels editable. */
function CircuitClass({ value, onChange }: { value?: string | null; onChange: (value: string) => void }) {
  const current = value || 'unspecified';
  const [editing, setEditing] = useState(false);
  const custom = editing || !CIRCUIT_CLASSES.includes(current);
  return <div className="circuit-class">
    <label title="What kind of circuit this is: opamp, ldo, vco, ... A label for your records. Results tables are grouped by it, and the validator uses it to check a claim such as 'tested on an unseen circuit class'.">Circuit class
    <select value={custom ? '' : current} onChange={e => {
      setEditing(e.target.value === '');
      if (e.target.value) onChange(e.target.value);
    }}>
      {CIRCUIT_CLASSES.map(c => <option key={c} value={c}>{c}</option>)}
      <option value="">Custom...</option>
    </select></label>
    {custom && <label>Custom circuit class<Typed spellCheck={false} value={current}
      format={v => v ?? ''} parse={text => ({ value: text || 'unspecified' })}
      onChange={v => { setEditing(true); onChange(v); }} /></label>}
  </div>;
}


/** Asked before a cell is read (window.confirm, the project's confirmation style): the workbench writes into the cell it
 *  reads, so it has to be a copy the user made. OK = read it and work in it; Cancel = read nothing. */
const copyQuestion = (r: Json) => `Work in ${r.library}/${r.cell} directly?\n\n`
  + 'The workbench makes no copy of its own. It writes into the cell it reads: saving a task writes the Maestro test GATOR into '
  + `${r.testbench_cell ? `the testbench ${r.testbench_cell}` : 'its testbench'}, and every run sets device sizes in ${r.cell} (put back when the run `
  + 'ends; a forced abort can leave them changed).\n\n'
  + 'So only read a COPY you made in Virtuoso (Library Manager: copy the cell and its testbench into a library of yours).\n\n'
  + `OK = ${r.library}/${r.cell} is such a copy: read it and work in it.\nCancel = read nothing.`;

/** The header's title block (record 7.158): what the page works on, as a drawing names its subject - since record 7.360
 *  (Draft A of the Roadster look, which the user chose: the banner names the task) the task as the Task window names it, then
 *  one line of its facts: the circuit's class and PDK labels and the label the RL model is saved under (record 7.159). The
 *  saved task's revision left it in record 7.372: the task's chip on the editors' tab line says it. The task name had left the header on 2026-10-05 (record 7.182); the chosen draft brings it back.
 *  Read-only; the fields themselves stay in their panels.
 *  Only a followed task gives the project's task name (branch record SIF-88): a fresh page titled itself "task" (the empty
 *  configuration's name) with "RL model task", and a Virtuoso cell kept the name of the last task loaded. A cell is named as
 *  the Next line beside Start names it, library/cell.
 *  A page that follows neither a task nor a cell has no facts to give (states audit of 2026-10-24, branch record SIF-139): it
 *  read "no task chosen   unspecified · unspecified · not set", the look hiding the keys. A label left at the configuration's
 *  default reads as words, "no class" or "no PDK". */
function TitleFacts({ config, task }: { config: Json; task: Json | null }) {
  const ref = config.circuit;
  const followed = ref.source === 'registered_task' && !!ref.task_id;
  const name = followed ? shownName(task, ref.task_id) : ref.source === 'virtuoso'
    ? (ref.cell ? `${ref.library}/${ref.cell} (not saved)` : 'choosing a Virtuoso cell') : 'no task chosen';
  const model = (config.run.model_label ?? '').trim() || (followed ? config.project.task_name : 'not set');
  const fact = (key: string, value: string, extra = '') => <span className={`tb-cell${extra}`}><span className="tb-k">{key}</span><span className="tb-v" title={`${key}: ${value}`}>{value}</span></span>;
  const label = (value: string | null | undefined, none: string) => !value || value === 'unspecified' ? none : value;
  return <><span className="tb-task" title={followed ? ref.task_id : name}>{name}</span>
    {(followed || ref.source === 'virtuoso') && <span className="tb-details">{fact('Class · PDK', `${label(ref.circuit_class, 'no class')} · ${label(ref.pdk_id, 'no PDK')}`)}
      {fact('RL model', model, ' tb-model')}</span>}</>;
}

export type { TaskLoad, TaskLoaded } from './taskChoice';

/** `schema`: /api/schema, for the row a size of a Virtuoso draft becomes (branch record SIF-104: Add's own, editorRules.ts newRow);
 *  without it the sizes have no "Add to Parameters". */
function CircuitPanelBody({ config, setConfig, circuit, setCircuit, profileId, schema = null, taskSlot, taskNotes, taskHead = null, taskTools = null, taskStatus = null,
  titleSlot = null, taskEpoch = 0, runs = [], refreshRuns, taskLoad, onTaskName }:
  { config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; circuit: Json; setCircuit: (c: Json) => void; profileId: string | null; schema?: Json;
    taskSlot: HTMLElement | null; taskNotes: HTMLElement | null; taskHead?: HTMLElement | null; taskTools?: HTMLElement | null; taskStatus?: HTMLElement | null;
    titleSlot?: HTMLElement | null; taskEpoch?: number; runs?: Json[]; refreshRuns?: () => Promise<Json[]>; taskLoad?: MutableRefObject<TaskLoad | null>;
    onTaskName?: (name: string | null) => void }) {
  const [tasks, setTasks] = useState<Json[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [nativeOpen, setNativeOpen] = useState(false);                    // closed until asked for; the choice then lasts across cells and Refresh
  const [hierarchyOpen, setHierarchyOpen] = useState(false);              // the whole Hierarchy block is one closed line; same rule
  const ngspiceOpen = useRef<((from?: Window | null) => void) | null>(null);   // the ngspice window's opener (NgspiceButton, record 7.362)
  const [ngspiceBlocked, setNgspiceBlocked] = useState(false);
  const ref = config.circuit;
  const offered = SOURCES.includes(ref.source);     // false: a saved configuration names the removed netlist source
  const virtuosoOn = ref.source === 'virtuoso';     // the page follows a Virtuoso cell (the window's work), not a task
  // The window's own choice: what the configuration says while the page follows a Virtuoso cell; blank while it follows a
  // task. A library chosen in the window then switches the page to the cell, as choosing the source used to.
  const chosen: Json = virtuosoOn ? ref : { library: null, cell: null, testbench_cell: null };
  const request = useNewest();                      // only the newest load may answer
  const followNext = useRef<'choice' | 'press' | null>(null);   // the next load answers a choice or a Read press: Probes may follow it
  const latest = useRef(config);                    // the configuration as it is NOW, for answers that arrive later
  latest.current = config;
  const patch = (fields: Json, follow: 'choice' | 'press' | null = null) => {
    if (follow) followNext.current = follow;
    setConfig(c => ({ ...c, circuit: { ...c.circuit, ...fields } }));
  };
  // The Virtuoso window: one named pop-up, drawn through a portal (popupWindow.ts, as the connection window is).
  const { popup, root, blocked, open: openWindow } = usePopupWindow('gator-virtuoso',
    { title: VIRTUOSO_WINDOW, features: 'popup,width=720,height=980', rootId: 'virtuoso-root' });

  useEffect(() => { tasksShared().then(t => setTasks(t.tasks)).catch(e => setError(e.message)); }, []);
  // follow: 'choice' (a library / cell / testbench was chosen) or 'press' (the cell was read): a Virtuoso draft that loads
  // then brings the Probes of the testbench it was read through (followTestbench).
  const load = async (reference: Json, follow: 'choice' | 'press' | null = null) => {
    const mine = request.next();
    setError(null);
    try {
      const loaded = await api.loadCircuit(reference);
      if (mine()) { setCircuit(loaded); if (follow) followTestbench(loaded, follow === 'press'); }
    }
    catch (e: any) { if (mine()) { setError(e.message); setCircuit(null); } }
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
    if (!offered) { request.drop(); setError(null); setCircuit(null); return; }
    // Another task - or the first look - loads at once. A change within the same one waits 0.4 s to settle: arrowing
    // through the Cell list of the Virtuoso window chose every cell on the way, and a cell's load may ask the bridge.
    // The previous cell's load still on its way is no longer this reference's: its answer was shown under the new cell
    // during those 0.4 s (review of 2026-10-01).
    request.drop();
    const task = `${ref.source}|${ref.task_id}`, settle = loadedAs.current === task ? 400 : 0;
    const timer = setTimeout(() => { loadedAs.current = task; load(ref, follow && virtuosoOn ? follow : null); }, settle);
    return () => clearTimeout(timer);
  }, [loadKey]);
  // A run that came to rest in the header may have changed what the task knows about itself - a finished Single baseline
  // simulation records the task's reference by itself (status record 7.78) - so the task is read again: local files, free.
  useEffect(() => { if (taskEpoch && offered && ref.source === 'registered_task') load(ref); }, [taskEpoch]);

  const { native, libraries, cells, chosenCell, listing, nativeError, nativeGated, setNativeError, nativeProblem, setRefresh } =
    useVirtuosoBrowser(!!popup, profileId, chosen, setConfig);
  // Save task (TaskSave.tsx): the editors' rows become the task real:<name>, which runs in the cell that was read. After a
  // first save the column switches to the task; after saving the open task again it is loaded again (its baseline may no
  // longer hold).
  const [saved, setSaved] = useState<Json>(null);          // the last first save: said again once the task is open
  const refreshTasks = () => tasksShared(true).then(t => setTasks(t.tasks)).catch(() => undefined);   // after a save or a delete: anew
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
  const { taskCheck, profileMessage, generatedName, deletableName, profileBusy, checkTask, setDeleted, deleteProfile, deletedHere, showVirtuoso,
    showNgspice, ngspiceTask, deleteNgspice } = useTaskActions({ ref, virtuosoOn, config, setConfig, circuit, profileId, tasks, setTasks, latest,
    refreshTasks, chooseTask: (key: string) => chooseTask(key) });
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
    // A first read needs the testbench (the backend's guard stays): said before the question, with nothing sent - also for
    // "Read the cell again" on a cell read before the question.
    if (declare && !ref.testbench_cell) { setNativeError(NO_TESTBENCH); return; }
    // Asked in the window that was clicked (the Virtuoso window): the main window's dialog opened behind it.
    if (declare && !(popup ?? window).confirm(copyQuestion(ref))) return;
    setImporting(true); setNativeError(null);
    try {
      const answer = await api.nativeImport(profileId!, ref.library, ref.cell, ref.testbench_cell ?? null, declare);
      if (answer?.pdk?.state === 'read') pdksChanged();  // the Components list in the RL model window shows it at once
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
  // A testbench chosen answers the line (branch record SIF-88); what another step said stays.
  useEffect(() => { if (ref.testbench_cell) setNativeError(e => (e === NO_TESTBENCH ? null : e)); }, [ref.testbench_cell]);

  const { followTestbench, takeTestbenchProbes, followCount, noteHere } = useTestbenchProbes({ ref, latest, setConfig });

  const { taskRows, taskLoading, taskLoadError, removedMock, chooseTask } = useTaskChoice({ ref, tasks, latest, setConfig, request, followCount,
    setCircuit, load, taskLoad });
  // "Reload saved values" asked by the summary of the rows not saved (record 7.372, Editors.tsx): the open task's saved rows,
  // asking first, as the same button under the toolbar does.
  const reloadNow = useRef(() => {});
  reloadNow.current = () => { const now = latest.current.circuit; if (now.source === 'registered_task' && now.task_id) chooseTask(now.task_id, undefined, true); };
  useEffect(() => {
    const reload = () => reloadNow.current();
    window.addEventListener(RELOAD_SAVED_REQUEST, reload);
    return () => window.removeEventListener(RELOAD_SAVED_REQUEST, reload);
  }, []);
  // A cell that already has a registered task - the task saved from it, or one of the verified built-in circuits - gets
  // no second task: the note names the task. One short button, because it is about THIS cell (not a list of tasks); it
  // does what choosing the task in the Project column does.
  const builtIn = circuit?.profile_task_generated === false;
  const taskNote = circuit?.profile_task && virtuosoOn ? (
    <div className="note">
      {/* A full stop after the key or its remark (states audit of 2026-10-24, branch record SIF-133): it ran into "Choose it". */}
      <p><b>This cell already has a registered task:</b> <code>{circuit.profile_task}</code>{builtIn ? ' (a verified built-in circuit)' : ''}.{' '}
        Choose it in the Tasks window (the task's name on the editors' tab line).</p>
      <details className="more"><summary>What this means</summary>
        <p>The workbench can already optimize this cell - through that task, in the Tasks window.{builtIn ? ' A verified built-in circuit gets no second task.'
          : ' Open it and use Save as to store edited rows as a new task with its own copy. To start over from this cell, open the task and press Delete task.'}</p></details>
    </div>) : null;
  // What was read straight from Virtuoso. It is a line of the Hierarchy block; while no circuit is loaded (browse only)
  // there is no such block and it stands alone at the end of the window.
  const nativeSchematic = <NativeSchematic native={native} open={nativeOpen} setOpen={setNativeOpen} />;
  // "Add to Parameters" after a size of the cell read (branch record SIF-104): the row Add makes, with the instance and the
  // parameter, in the parameter's unit, as one Undo step. Only for a draft that Save as can make a task of (sizesAddable): a
  // cell that has a task already gets none (taskNote), and a task's own rows come from the task. Its initial value stays empty
  // - the value the circuit has - as on every row made in the page (review of SIF-104): a stated one is checked against the
  // circuit and can be neither seen nor typed, so once the Parameter was typed again, or the cell read again after a change in
  // Virtuoso, the present value the press gave it marked the row ("Configuration says 4 um but the circuit has 180 nm") until
  // the row was deleted.
  const adding: SizeAdding | undefined = schema && sizesAddable(config, circuit) && circuit?.loaded && circuit.native_draft ? {
    rows: config.parameters ?? [],
    add: (instance_path, parameter_name) => {
      const base = newRow('parameters', latest.current, schema);
      const row = { ...base, instance_path, parameter_name, unit: kindUnit(parameter_name) ?? base.unit };
      setConfig(c => ({ ...c, parameters: [...(c.parameters ?? []), row] }));
      return String(row.variable_id);
    } } : undefined;
  const circuitInfo = <CircuitDetails circuit={circuit} open={hierarchyOpen} setOpen={setHierarchyOpen} adding={adding}>
    {virtuosoOn && nativeSchematic}</CircuitDetails>;

  // ---- the task on the editors' tab line, its own lines under the toolbar, and the circuit column (record 7.362) -----------
  // The user's Option D ("go with D"): the editors are the task's card. The task's name - the button that opens the Tasks
  // window - and its revision start the tab line; Check now stands before Save task at its end; what the task says about
  // itself (loading, blocked, MOCK, its baseline, the check's result) stands under the toolbar. The circuit column holds the
  // circuit alone - labels, picture, notes, hierarchy - folded away until "Show circuit". The two ways to a new task, a
  // Virtuoso cell and an ngspice netlist, are in the Tasks window ("New task"); while the page follows a Virtuoso cell or an
  // ngspice task, the button back to its window is on the tab line too.
  const current = ref.source === 'registered_task' && ref.task_id && !removedMock ? ref.task_id : null;
  // A rename of the task the page follows (Tasks window, record 7.302) gives its run label at once (branch record SIF-100):
  // new runs kept the old name until the task was chosen again, which asks to discard edits. No Undo step: a label only.
  const renamedTask = (key: string, label: string) => setConfig(c => (c.circuit?.source === 'registered_task' && c.circuit.task_id === key
    && c.project?.task_name !== label ? { ...c, project: { ...c.project, task_name: label } } : c), false);
  const currentTask: Json = current ? tasks.find(t => t.task_key === current) ?? null : null;
  const revision: number | null = currentTask?.revision ?? null;
  const newTask = showVirtuoso || showNgspice ? (owner: Window) => <>
    {showVirtuoso && <button className="virtuoso-button" onClick={() => openWindow(owner)}
      title={popup ? 'The Virtuoso window is open: press to bring it to the front.' : `From a Virtuoso cell: ${VIRTUOSO_OPENS}`}>From a Virtuoso cell...</button>}
    {showVirtuoso && blocked && <Blocked />}
    {showNgspice && <button className="ngspice-button" onClick={() => ngspiceOpen.current?.(owner)} title={`From an ngspice netlist: ${NGSPICE_OPENS}`}>From an ngspice netlist...</button>}
    {showNgspice && ngspiceBlocked && <Blocked />}
  </> : undefined;
  const head = taskHead && createPortal(
    <span className="row task-row" title="The task the editors and a run are about; its name opens the Tasks window. A cell read from Virtuoso becomes one of these with Save as.">
      <span className="task-caption">Task</span>
      <TaskListButton tasks={tasks} runs={runs} ngspiceOffered={showNgspice} loading={taskLoading} onChoose={(key, owner) => chooseTask(key, undefined, false, undefined, undefined, owner)}
        onRefresh={() => tasksShared(true).then(t => { setTasks(t.tasks); return t.tasks; })} onRefreshRuns={refreshRuns}
        onRenamed={renamedTask} current={current}
        currentMark={current ? taskMark(currentTask ?? { kind: 'real', available: true }, showNgspice) : undefined}
        currentMarkTitle={currentTask?.blocker ?? undefined}
        onDelete={current && (deletableName || ngspiceTask) ? (ngspiceTask ? deleteNgspice : deleteProfile) : undefined}
        deleting={profileBusy === 'delete'} deleteDisabled={!!profileBusy}
        deleteTitle={ngspiceTask ? 'Delete task: Asks once more. The task leaves the Tasks window; its deck and task file are kept aside on the backend machine, and runs already made keep their data.'
          : 'Delete task: Asks once more. The task leaves the Tasks window and its cell can get a new one; its files are kept aside on the backend machine, and runs already made keep their data.'}
        deleteNotice={profileMessage?.what === 'delete' && <p className={profileMessage.level === 'ok' ? 'ok' : 'error'}>{profileMessage.text}</p>}
        currentText={ref.source !== 'registered_task' ? (virtuosoOn ? (ref.cell ? `(none: ${ref.library}/${ref.cell} is read from Virtuoso)` : '(none: a Virtuoso cell is being chosen)')
          : '(none: the saved source was removed)') : !ref.task_id ? '(choose a task)' : `${ref.task_id} (removed)`}
        newTask={newTask} />
      {revision != null && <span className="task-rev" title={`Revision ${revision} of the saved task.`}>rev. {revision}</span>}
    </span>, taskHead);
  const tools = taskTools && createPortal(<>
    {virtuosoOn && showVirtuoso && <button className="virtuoso-button" onClick={() => openWindow()}
      title={popup ? 'The Virtuoso window is open: press to bring it to the front.' : `Virtuoso cell: back to the cell the page follows. ${VIRTUOSO_OPENS}`}>Virtuoso cell...</button>}
    {ngspiceTask && showNgspice && <button className="ngspice-button" onClick={() => ngspiceOpen.current?.()}
      title={`ngspice netlist: the deck of this task; saving stores its next revision. ${NGSPICE_OPENS}`}>ngspice netlist...</button>}
    {generatedName && <button className="check-now" disabled={!!profileBusy} onClick={checkTask} title={CHECK_NOW}>
      {profileBusy === 'check' ? 'Checking...' : 'Check now'}</button>}
  </>, taskTools);
  const status = taskStatus && createPortal(<>
    {/* Spectre netlist files only, as the backend's refusal says (states audit of 2026-10-24, branch record SIF-139): "no longer
        imports netlists" stood beside the Tasks window's "From an ngspice netlist...", which that way names. Each way to a new
        task is named only while that window offers it (review of SIF-139: the Virtuoso cell was named with an ngspice
        connection in use, whose New task row has no "From a Virtuoso cell..."). */}
    {!offered && <div className="note"><p>This configuration was saved with a Spectre netlist file{ref.netlist_path ? <> (<code>{ref.netlist_path}</code>)</> : null}.
      The workbench no longer imports Spectre netlist files (.scs): choose a task{showVirtuoso ? ' or a Virtuoso cell' : ''} in the Tasks window (the task's name on this tab line).
      {showNgspice ? ' A SPICE deck for ngspice can become a task there: New task, From an ngspice netlist...' : ''}</p></div>}
    {/* No task yet (record 7.372): the ways to one, here, instead of a lone "(choose a task)" on the tab line. */}
    {ref.source === 'registered_task' && !ref.task_id && <div className="task-start">
      <p>No task yet: choose one in the Tasks window, or make one.</p>
      <div className="row">
        <button className="open-tasks" onClick={() => openTasksAt({})} title="Open Tasks: every registered task; a double click makes the page follow one.">Open Tasks</button>
        {showVirtuoso && <button className="new-virtuoso" onClick={() => openWindow()} title={`From a Virtuoso cell: ${VIRTUOSO_OPENS}`}>From a Virtuoso cell...</button>}
        {showNgspice && <button className="new-ngspice" onClick={() => ngspiceOpen.current?.()} title={`From an ngspice netlist: ${NGSPICE_OPENS}`}>From an ngspice netlist...</button>}
      </div>
      {showVirtuoso && blocked && <Blocked />}{showNgspice && ngspiceBlocked && <Blocked />}
    </div>}
    {ref.source === 'registered_task' && (<>
      {/* A configuration saved with a removed MOCK task (the four of status record 7.59; the last one, synthetic:gpdk045_ota5,
          on 2026-09-30, record 7.128): a plain note, not a red "Blocked". */}
      {removedMock && <div className="note"><p><code>{ref.task_id}</code> no longer exists: the workbench has no MOCK task since
        2026-09-30. Choose one of your saved tasks in the Tasks window; it brings its own rows.</p></div>}
      {!taskLoading && taskRows?.task === ref.task_id && sameRows(config, taskRows!.starter) && <p className="hint task-rows">Parameters, Probes and Specs now show this task's rows
            {taskRows!.starter.targets.length ? '' : ' - it has no targets of record, so Specs is yours to fill (its results are ready in Probes)'}. Undo brings the previous ones back.</p>}
    </>)}
    {taskLoading && <p className="hint task-rows" role="status">Loading <code>{taskLoading}</code>...</p>}
    {taskLoadError && <p className="error task-rows" role="alert">{taskLoadError}</p>}
    {virtuosoOn && showVirtuoso && blocked && <Blocked />}
    {ngspiceTask && showNgspice && ngspiceBlocked && <Blocked />}
    {deletedHere && !circuit?.profile_task && (<>
      <p className="ok">Task <code>{deletedHere.deleted}</code> deleted. Its cell <code>{deletedHere.library}/{deletedHere.cell}</code> can get a new one (Tasks window: New task, From a Virtuoso cell...).</p>
      <details className="more hint"><summary>Where its files went</summary>
        <p>Nothing was erased. They are kept on the backend machine in <code>{deletedHere.kept_copy}</code>.</p></details>
    </>)}
    {error && <p className="error">{error}</p>}
    {ref.source === 'registered_task' && circuit && !circuit.loaded && !removedMock && <div className="blocker"><b>Blocked:</b> {circuit.blocker}
      {circuit.interface_contract && <details><summary>Interface contract</summary><pre>{JSON.stringify(circuit.interface_contract, null, 1)}</pre></details>}</div>}
    {ref.source === 'registered_task' && circuit?.loaded && (<>
      {circuit.mock && <p className="mock">MOCK evaluation backend: {circuit.evaluation_backend}</p>}
      {circuit.simulator === 'ngspice' && (<>
        <p className="real">ngspice evaluation backend: every evaluation is one real circuit simulation by ngspice (no license). Start asks you to
          confirm the number of simulations first.</p>
        {/* The line that sends the user to the Connection window carries the button to it (states audit of 2026-10-24, branch
            record SIF-139), as SIF-108's lines in the Virtuoso and Agent windows do: with a connection chosen the header's pill
            shows its name, the word "Connection" for screen readers only. Opening the window checks nothing. */}
        {circuit.circuit?.connection_problem && <div className="line-act connection-problem"><p className="warn">{circuit.circuit.connection_problem}</p>
          <button className="open-connection" onClick={() => openConnection()}
            title="Connection: Opens the Connection window, as the connection button in the header does: choose or add an ngspice connection there and test it. Opening it checks nothing.">Connection...</button></div>}
      </>)}
      <TaskBaseline key={circuit.task_key} circuit={circuit} config={config} refresh={() => load(ref)} />
      {/* The cell a run sets sizes in, then its testbench (states audit of 2026-10-24, branch record SIF-133): the line named
          the testbench alone, as if the sizes were written there. */}
      {saved && saved.task_key === ref.task_id && <p className="ok">Saved the new task <code>{saved.task_key}</code>. It runs in{' '}
        <code>{saved.copy?.library}/{saved.copy?.cell}</code>{saved.copy?.testbench && saved.copy.testbench !== saved.copy.cell
          ? <> with its testbench <code>{saved.copy.testbench}</code></> : ''}{saved.copy?.library === saved.original?.library && saved.copy?.cell === saved.original?.cell ? ' - the cell you declared as your copy' : ' - its working copy'}.{baselineText(saved)}</p>}
      {generatedName && taskCheck && <CheckSteps result={taskCheck} />}
      {generatedName && profileMessage && profileMessage.what !== 'delete' && <p className={profileMessage.level === 'ok' ? 'ok' : 'error'}>{profileMessage.text}</p>}
    </>)}
  </>, taskStatus);
  // The circuit column: the circuit alone, beside the rows on request ("Show circuit", App.tsx).
  const column = (
    <section className="panel circuit-panel">
      <h3>Circuit</h3>
      {/* The labels of the circuit, saved with every run: one folded line whose text names them. */}
      <details className="more hint labels"><summary>Labels: class <b>{ref.circuit_class ?? 'unspecified'}</b>, PDK <b>{ref.pdk_id ?? 'unspecified'}</b></summary>
        <div className="row circuit-labels">
          <CircuitClass value={ref.circuit_class} onChange={v => patch({ circuit_class: v })} />
          <label title="Which process design kit (technology) the circuit is built in, e.g. gpdk045. Written into the run records so a result can be traced to its technology. PDK files are never copied.">PDK id
            <Typed value={ref.pdk_id} format={v => v ?? ''} parse={t => ({ value: t || 'unspecified' })} onChange={v => patch({ pdk_id: v })} /></label>
        </div>
        <p>Circuit class and PDK id are labels saved with every run. They do not change the simulation or the optimization;
          "unspecified" is fine for a single run. A task brings its own; a cell read from Virtuoso brings the PDK id of its library's technology library.</p>
      </details>
      {ref.source === 'registered_task' && circuit?.loaded ? (<>
        {circuit.simulator === 'ngspice' && <div className="note">
          <p><b>ngspice netlist task</b>, revision {circuit.circuit?.revision ?? '?'}{circuit.circuit?.title ? <>: <i>{circuit.circuit.title}</i></> : null}.
            {' '}{plural((circuit.circuit?.measurements ?? []).length, 'result')}: <code>{(circuit.circuit?.measurements ?? []).join(', ')}</code>.</p>
          <details className="more"><summary>How it runs</summary>
            <p>Each evaluation writes the chosen sizes into their own places in the deck, runs <code>ngspice -b</code> on it through the ngspice
              connection (on this machine, or over SSH with the deck sent in), and reads the <code>name = value</code> lines it prints. To change
              the deck, press <b>ngspice netlist...</b> on the editors' tab line (shown while an ngspice connection is in use): saving stores the
              next revision (runs made before keep their own copy).</p></details>
        </div>}
        {/* The circuit picture (record 7.158) above the long notes, so it is in view while Parameters rows are pointed at. */}
        <CircuitPicture circuit={circuit} />
        {circuitInfo}
      </>) : <p className="hint">{virtuosoOn ? 'A cell read from Virtuoso shows its hierarchy in the Virtuoso window (Virtuoso cell... on the tab line).'
        : 'The picture and the hierarchy of the task show here once it is loaded.'}</p>}
    </section>);
  const taskSave = generatedName && (
    <TaskSave profileId={profileId} library={null} cell={null} task={generatedName} hasCopy
      config={config} setConfig={setConfig} onSaved={taskSaved} onSavedElsewhere={savedElsewhere}
      onReload={() => chooseTask(ref.task_id, undefined, true)} bar={taskSlot} notes={taskNotes} />);
  // The ngspice window and its work stay with the page; its buttons are in the Tasks window and on the tab line.
  const ngspiceWindow = showNgspice && <NgspiceButton config={config} circuit={circuit} chooseTask={chooseTask} onTasksChanged={refreshTasks}
    button={false} openRef={ngspiceOpen} onBlocked={setNgspiceBlocked} />;

  // ---- the Virtuoso window: library / cell / testbench, the read, the setup, the first save: VirtuosoWindow.tsx --------------------
  // The first save of a cell read from Virtuoso. It lives with the column, not in the Virtuoso window: its buttons sit on
  // the editors' tab line and hold what waits for the save (task-file parts applied) - closing the window took that away
  // (audit 2026-09-30).
  const firstSave = virtuosoOn && circuit?.loaded && circuit.native_draft && !taskNote && (
    <TaskSave profileId={profileId} library={ref.library} cell={ref.cell} task={null} hasCopy={!!circuit.working_copy?.verified}
      config={config} setConfig={setConfig} onSaved={taskSaved} onSavedElsewhere={savedElsewhere} bar={taskSlot} notes={taskNotes} />);
  const followed = ref.source === 'registered_task' ? tasks.find(t => t.task_key === ref.task_id) ?? null : null;
  const titleFacts = titleSlot && createPortal(<TitleFacts config={config} task={followed} />, titleSlot);
  // The name the title gives the task, for the header's "Next:" line beside Start (branch record SIF-71: under the title
  // "ota_relaxed" it read "Next: fixture_ota · ...", the key of a task renamed in the Tasks window). Null: no registered task.
  const shownTask = ref.source === 'registered_task' && ref.task_id ? shownName(followed, ref.task_id) : null;
  useEffect(() => onTaskName?.(shownTask), [shownTask]);
  return <>{column}{head}{tools}{status}{taskSave}{firstSave}{titleFacts}{ngspiceWindow}<PopupPortal popup={popup} root={root}><VirtuosoWindow profileId={profileId} virtuosoOn={virtuosoOn} offered={offered}
    circuitRef={ref} chosen={chosen} libraries={libraries} cells={cells} chosenCell={chosenCell} listing={listing} importing={importing} patch={patch} setRefresh={setRefresh}
    pdkStep={pdkStep} nativeError={nativeError} nativeGated={nativeGated} error={error} circuit={circuit} taskNote={taskNote} importCell={importCell} config={config} setConfig={setConfig}
    noteHere={noteHere} takeTestbenchProbes={takeTestbenchProbes} circuitInfo={circuitInfo} native={native} nativeSchematic={nativeSchematic} /></PopupPortal></>;
}

/** Memoised (record 7.275): its props change with the configuration, the circuit, the run list and the task - not with
 *  the status polled every 1.5 s while a run works, which drew the whole column (and the windows it holds) at every update.
 *  App.tsx hands it a stable `refreshRuns` for that. */
export const CircuitPanel = memo(CircuitPanelBody);
