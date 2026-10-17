import { CircuitDetails, NativeSchematic, useVirtuosoBrowser } from './CircuitBrowser';
import { memo, MutableRefObject, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, Json } from '../api';
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
import { type TaskLoad, useTaskChoice } from './taskChoice';
import { VirtuosoWindow } from './VirtuosoWindow';

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

const CIRCUIT_CLASSES = ['opamp', 'ldo', 'vco', 'bandgap', 'comparator', 'oscillator', 'unspecified'];
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
 *  one line of its facts: the circuit's class and PDK labels, the saved task's revision, and the label the RL model is saved
 *  under (record 7.159). The task name had left the header on 2026-10-05 (record 7.182); the chosen draft brings it back.
 *  Read-only; the fields themselves stay in their panels. */
function TitleFacts({ config, task }: { config: Json; task: Json | null }) {
  const ref = config.circuit;
  const name = ref.source === 'registered_task' && ref.task_id ? shownName(task, ref.task_id) : (config.project.task_name || 'no task chosen');
  const revision = task?.revision ?? null;
  const model = (config.run.model_label ?? '').trim() || config.project.task_name;
  const fact = (key: string, value: string, extra = '') => <span className={`tb-cell${extra}`}><span className="tb-k">{key}</span><span className="tb-v" title={`${key}: ${value}`}>{value}</span></span>;
  return <><span className="tb-task" title={ref.task_id ?? name}>{name}</span>
    <span className="tb-details">{fact('Class · PDK', `${ref.circuit_class ?? 'unspecified'} · ${ref.pdk_id ?? 'unspecified'}`)}
      {fact('Rev', revision == null ? '-' : String(revision), ' tb-rev')}{fact('RL model', model, ' tb-model')}</span></>;
}

export type { TaskLoad, TaskLoaded } from './taskChoice';

function CircuitPanelBody({ config, setConfig, circuit, setCircuit, profileId, taskSlot, taskNotes, titleSlot = null, taskEpoch = 0, runs = [], refreshRuns, taskLoad }:
  { config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; circuit: Json; setCircuit: (c: Json) => void; profileId: string | null;
    taskSlot: HTMLElement | null; taskNotes: HTMLElement | null;
    titleSlot?: HTMLElement | null; taskEpoch?: number; runs?: Json[]; refreshRuns?: () => Promise<Json[]>; taskLoad?: MutableRefObject<TaskLoad | null> }) {
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

  const { native, libraries, cells, chosenCell, listing, nativeError, setNativeError, nativeProblem, setRefresh } =
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

  const { followTestbench, takeTestbenchProbes, followCount, noteHere } = useTestbenchProbes({ ref, latest, setConfig });

  const { taskRows, taskLoading, taskLoadError, removedMock, chooseTask } = useTaskChoice({ ref, tasks, latest, setConfig, request, followCount,
    setCircuit, load, taskLoad });
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
          : ' Open it and use Save as to store edited rows as a new task with its own copy. To start over from this cell, open the task and press Delete task.'}</p></details>
    </div>) : null;
  // What was read straight from Virtuoso. It is a line of the Hierarchy block; while no circuit is loaded (browse only)
  // there is no such block and it stands alone at the end of the window.
  const nativeSchematic = <NativeSchematic native={native} open={nativeOpen} setOpen={setNativeOpen} />;
  const circuitInfo = <CircuitDetails circuit={circuit} open={hierarchyOpen} setOpen={setHierarchyOpen}>
    {virtuosoOn && nativeSchematic}</CircuitDetails>;

  // ---- the left column: the project and the registered task --------------------------------------------------------------
  const column = (
    <section className="panel">
      {/* No Project name box (record 7.159, user: "remove the project name box in the Project module"): the name only filed
          the last run, which the RL model's own label in the RL model window does now. */}
      <h3>Registered task</h3>
      {!offered && <div className="note"><p>This configuration was saved with a Spectre netlist file{ref.netlist_path ? <> (<code>{ref.netlist_path}</code>)</> : null}.
        The workbench no longer imports netlists: choose a task below, or a Virtuoso cell in its window.</p></div>}
      {/* The task name is the button that opens the Tasks window. Choosing a row there loads its saved settings. */}
      <div className="row task-row" title="The circuit the editors and a run are about. A cell read from Virtuoso becomes one of these with Save as.">
        <span className="task-caption">Task</span>
        <TaskListButton tasks={tasks} runs={runs} ngspiceOffered={showNgspice} loading={taskLoading} onChoose={key => chooseTask(key)}
          onRefresh={() => tasksShared(true).then(t => { setTasks(t.tasks); return t.tasks; })} onRefreshRuns={refreshRuns}
          current={ref.source === 'registered_task' && ref.task_id && !removedMock ? ref.task_id : null}
          currentMark={ref.source === 'registered_task' && ref.task_id && !removedMock ? taskMark(tasks.find(t => t.task_key === ref.task_id) ?? { kind: 'real', available: true }, showNgspice) : undefined}
          onDelete={ref.source === 'registered_task' && ref.task_id && !removedMock && (deletableName || ngspiceTask) ? (ngspiceTask ? deleteNgspice : deleteProfile) : undefined}
          deleting={profileBusy === 'delete'} deleteDisabled={!!profileBusy}
          deleteTitle={ngspiceTask ? 'Delete task: Asks once more. The task leaves the Registered task list; its deck and task file are kept aside on the backend machine, and runs already made keep their data.'
            : 'Delete task: Asks once more. The task leaves the Registered task list and its cell can get a new one; its files are kept aside on the backend machine, and runs already made keep their data.'}
          deleteNotice={profileMessage?.what === 'delete' && <p className={profileMessage.level === 'ok' ? 'ok' : 'error'}>{profileMessage.text}</p>}
          currentText={ref.source !== 'registered_task' ? (virtuosoOn ? (ref.cell ? `(none: ${ref.library}/${ref.cell} is read from Virtuoso)` : '(none: a Virtuoso cell is being chosen)')
            : '(none: the saved source was removed)') : !ref.task_id ? '(choose a task)' : `${ref.task_id} (removed)`} />
      </div>
      {ref.source === 'registered_task' && (<>
        {/* A configuration saved with a removed MOCK task (the four of status record 7.59; the last one, synthetic:gpdk045_ota5,
            on 2026-09-30, record 7.128): a plain note, not a red "Blocked". */}
        {removedMock && <div className="note"><p><code>{ref.task_id}</code> no longer exists: the workbench has no MOCK task since
          2026-09-30. Choose one of your saved tasks under Task; it brings its own rows.</p></div>}
        {!taskLoading && taskRows?.task === ref.task_id && sameRows(config, taskRows!.starter) && <p className="hint task-rows">Parameters, Probes and Specs now show this task's rows
              {taskRows!.starter.targets.length ? '' : ' - it has no targets of record, so Specs is yours to fill (its results are ready in Probes)'}. Undo brings the previous ones back.</p>}
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
        {showVirtuoso && blocked && <Blocked />}
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
      <details className="more hint labels"><summary>Labels: class <b>{ref.circuit_class ?? 'unspecified'}</b>, PDK <b>{ref.pdk_id ?? 'unspecified'}</b></summary>
        <div className="row circuit-labels">
          <CircuitClass value={ref.circuit_class} onChange={v => patch({ circuit_class: v })} />
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
        <TaskBaseline key={circuit.task_key} circuit={circuit} config={config} refresh={() => load(ref)} />
        {saved && saved.task_key === ref.task_id && <p className="ok">Saved the new task <code>{saved.task_key}</code>. It runs in
          <code> {saved.copy?.library}/{saved.copy?.testbench}</code>{saved.copy?.library === saved.original?.library && saved.copy?.cell === saved.original?.cell ? ' - the cell you declared as your copy' : ' - its working copy'}.{baselineText(saved)}</p>}
        {/* The circuit picture (record 7.158) above the long note, so it is in view while Parameters rows are pointed at. */}
        <CircuitPicture circuit={circuit} />
        {generatedName && (
          <div className="note">
            <TaskSave profileId={profileId} library={null} cell={null} task={generatedName}
              revision={tasks.find(t => t.task_key === ref.task_id)?.revision ?? null} hasCopy
              config={config} setConfig={setConfig} onSaved={taskSaved} onSavedElsewhere={savedElsewhere}
              onReload={() => chooseTask(ref.task_id, undefined, true)} bar={taskSlot} notes={taskNotes} />
            {/* One line; the explanation is its tooltip (record 7.177, user: "reduce the texts this part"). */}
            <p title={'Start, Calibration and Resume first check that the editors, this saved task and its cell in Virtuoso agree. '
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

  // ---- the Virtuoso window: library / cell / testbench, the read, the setup, the first save: VirtuosoWindow.tsx --------------------
  // The first save of a cell read from Virtuoso. It lives with the column, not in the Virtuoso window: its buttons sit on
  // the editors' tab line and hold what waits for the save (task-file parts applied) - closing the window took that away
  // (audit 2026-09-30).
  const firstSave = virtuosoOn && circuit?.loaded && circuit.native_draft && !taskNote && (
    <TaskSave profileId={profileId} library={ref.library} cell={ref.cell} task={null} hasCopy={!!circuit.working_copy?.verified}
      config={config} setConfig={setConfig} onSaved={taskSaved} onSavedElsewhere={savedElsewhere} bar={taskSlot} notes={taskNotes} />);
  const titleFacts = titleSlot && createPortal(<TitleFacts config={config}
    task={ref.source === 'registered_task' ? tasks.find(t => t.task_key === ref.task_id) ?? null : null} />, titleSlot);
  return <>{column}{firstSave}{titleFacts}<PopupPortal popup={popup} root={root}><VirtuosoWindow profileId={profileId} virtuosoOn={virtuosoOn} offered={offered}
    circuitRef={ref} chosen={chosen} libraries={libraries} cells={cells} chosenCell={chosenCell} listing={listing} importing={importing} patch={patch} setRefresh={setRefresh}
    pdkStep={pdkStep} nativeError={nativeError} error={error} circuit={circuit} taskNote={taskNote} importCell={importCell} config={config} setConfig={setConfig}
    noteHere={noteHere} takeTestbenchProbes={takeTestbenchProbes} circuitInfo={circuitInfo} nativeSchematic={nativeSchematic} /></PopupPortal></>;
}

/** Memoised (record 7.275): its props change with the configuration, the circuit, the run list and the task - not with
 *  the status polled every 1.5 s while a run works, which drew the whole column (and the windows it holds) at every update.
 *  App.tsx hands it a stable `refreshRuns` for that. */
export const CircuitPanel = memo(CircuitPanelBody);
