import { useEffect, useRef, useState } from 'react';
import { api, Json } from '../api';
import { WorkingCopy } from './WorkingCopy';
import { TaskSave } from './TaskSave';
import { CheckSteps } from './Consistency';

/** The connection block lives in Connection.tsx: one button in this column that opens the connection window. */

/** A gate refusal in the words of this column. A connection of the wrong KIND (ngspice asked for a Virtuoso cell) is not
 *  a link that is down: the backend's own sentence says what to choose instead. */
const gateText = (gate: Json) => gate.blocking?.includes('connection_kind') ? (gate.next_steps?.[0] ?? 'This kind of connection cannot do that.')
  : `Virtuoso cannot be reached (${[...(gate.blocking ?? []), ...(gate.uncertain ?? [])].join(', ') || gate.status}). Bring the link up in the Connection window (the "Connection" button above), then try again.`;

function Tree({ node, path = '' }: { node: Json; path?: string }) {
  const keys = Object.keys(node);
  if (!keys.length) return null;
  return <ul className="tree">{keys.map(k => <li key={path + k}><span>{k}</span><Tree node={node[k]} path={path + k + '/'} /></li>)}</ul>;
}

/** Backend messages name the schema fields; the form shows labels. */
const FIELD_LABEL: Record<string, string> = { netlist_path: 'Netlist path', parser_config_path: 'Device mapping (JSON)' };
const labelled = (text: string) => text.replace(/\b(netlist_path|parser_config_path)\b/g, name => `"${FIELD_LABEL[name]}"`);
/** D:\folder\file -> /mnt/d/folder/file when the backend runs in WSL (its own paths start with "/"). */
const backendPath = (text: string, posixBackend: boolean) => {
  const drive = /^([A-Za-z]):[\\/](.*)$/.exec(text.trim());
  return posixBackend && drive ? `/mnt/${drive[1].toLowerCase()}/${drive[2].replace(/\\/g, '/')}` : text.trim();
};
/** A dropdown must be able to show the configured value even when the list does not (yet) contain it. */
const withCurrent = (names: string[], current?: string | null) => (current && !names.includes(current) ? [current, ...names] : names);
/** The testbench a cell's NAME points to: `tb_<cell>` in the listed library (the prefix in any case, the cell name exact),
 *  with a schematic. null when there is none. */
const namedTestbench = (cells: Json, cell?: string | null): string | null => {
  if (!cells || !cell) return null;
  const found = (cells.cells ?? []).filter((c: Json) => c.has_schematic && /^tb_/i.test(c.name) && c.name.slice(3) === cell).map((c: Json) => c.name);
  return found.find((name: string) => name === `tb_${cell}`) ?? found[0] ?? null;
};
const sameJson = (a: Json, b: Json) => JSON.stringify(a ?? []) === JSON.stringify(b ?? []);
const EXAMPLE_NETLIST = { netlist_path: 'tests/fixtures/synthetic/opamp.scs', parser_config_path: 'configs/opamp.json' };

/** What the Agent tab is asked once a cell was read from Virtuoso and copied. Shown in the message box first: editable, never sent by
 *  itself. The request kind is `virtuoso_setup`: the rows plus the Maestro setup of the working copy, written there after approval. */
const SETUP_PROMPT = 'Read this circuit and say in two or three sentences what it is and how it works. Then set it up for optimization in its '
  + 'working copy: which transistor widths to vary (grouped where devices must match) with sensible ranges, what to measure as Maestro outputs '
  + 'with the analyses they need, and specs on them. Add the requirements I give here: ';

/** The three editors, by their configuration keys: Parameters, Specs, Probes. */
const ROW_SECTIONS = ['parameters', 'targets', 'measurements'];
const sameRows = (config: Json, starter: Json) => ROW_SECTIONS.every(s => JSON.stringify(config[s] ?? []) === JSON.stringify(starter[s] ?? []));
const noRows = (config: Json) => ROW_SECTIONS.every(s => !(config[s] ?? []).length);

export function CircuitPanel({ config, setConfig, circuit, setCircuit, profileId, meta, onAgent }:
  { config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; circuit: Json; setCircuit: (c: Json) => void; profileId: string | null; meta: Json;
    onAgent: (kind: string, selection: Json[], prompt?: string) => void }) {
  const [tasks, setTasks] = useState<Json[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [native, setNative] = useState<Json>(null);
  const [nativeOpen, setNativeOpen] = useState(false);                    // closed until asked for; the choice then lasts across cells and Refresh
  const [hierarchyOpen, setHierarchyOpen] = useState(false);              // the whole Hierarchy block is one closed line; same rule
  const [libraries, setLibraries] = useState<string[] | null>(null);      // null = not listed (yet)
  const [cells, setCells] = useState<Json>(null);                         // { library, technology_library, cells: [{ name, views, has_schematic }] }
  const [listing, setListing] = useState<string | null>(null);            // what is being fetched from Virtuoso right now
  const [nativeError, setNativeError] = useState<Json>(null);             // { step, text, outdated }
  const [refresh, setRefresh] = useState(0);                              // repeats the whole chain
  const [loading, setLoading] = useState(false);
  const ref = config.circuit;
  const edited = useRef(false);                     // set by this panel's own inputs: typing must not load a netlist per keystroke
  const pressed = useRef<string | null>(null);      // the reference a button press is already loading
  const request = useRef(0);                        // only the newest load may answer
  const followNext = useRef(false);                 // the next load answers a choice of library / cell / testbench: Probes may follow it
  const latest = useRef(config);                    // the configuration as it is NOW, for answers that arrive later
  latest.current = config;
  const patch = (fields: Json, follow = false) => {
    edited.current = true;
    if (follow) followNext.current = true;
    setConfig(c => ({ ...c, circuit: { ...c.circuit, ...fields } }));
  };
  const netlistReady = !!ref.netlist_path?.trim() && !!ref.parser_config_path?.trim();
  const root = meta?.repo_root ? `${meta.repo_root}/` : '';     // absolute, so the example does not depend on where the backend was started
  const example = { netlist_path: root + EXAMPLE_NETLIST.netlist_path, parser_config_path: root + EXAMPLE_NETLIST.parser_config_path };

  useEffect(() => { api.tasks().then(t => setTasks(t.tasks)).catch(e => setError(e.message)); }, []);
  // follow: 'choice' (a library / cell / testbench was chosen) or 'press' (the cell was read): a Virtuoso draft that loads
  // then brings the Probes of the testbench it was read through (followTestbench).
  const load = async (reference: Json, follow: 'choice' | 'press' | null = null) => {
    const mine = ++request.current;
    setError(null); setLoading(true);
    try {
      const loaded = await api.loadCircuit(reference);
      if (mine === request.current) { setCircuit(loaded); if (follow) followTestbench(loaded, follow === 'press'); }
    }
    catch (e: any) { if (mine === request.current) { setError(labelled(e.message)); setCircuit(null); } }
    finally { if (mine === request.current) setLoading(false); }
  };
  useEffect(() => {
    const key = JSON.stringify(ref), typed = edited.current, follow = followNext.current;
    edited.current = false; followNext.current = false;
    if (pressed.current === key) { pressed.current = null; return; }
    // A netlist is loaded by its button (or Enter), never while its paths are being typed or still missing: asking the
    // backend then only produced "Blocked: needs netlist_path ..." the moment the source was chosen. Whatever was
    // loaded before no longer belongs to this reference, so it is cleared. A complete reference that arrives from
    // outside this panel (imported configuration, approved proposal) still loads by itself, like a registered task.
    if (ref.source === 'netlist' && (typed || !netlistReady)) { request.current++; setLoading(false); setError(null); setCircuit(null); return; }
    load(ref, follow && ref.source === 'virtuoso' ? 'choice' : null);
  }, [JSON.stringify(ref)]);
  const loadNetlist = (fields: Json = {}) => {
    const posix = (meta?.repo_root ?? '/').startsWith('/');
    const wanted = { ...ref, ...fields };
    const fixed = { ...wanted, netlist_path: backendPath(wanted.netlist_path ?? '', posix), parser_config_path: backendPath(wanted.parser_config_path ?? '', posix) };
    if (JSON.stringify(fixed) !== JSON.stringify(ref)) { pressed.current = JSON.stringify(fixed); setConfig(c => ({ ...c, circuit: fixed })); }
    load(fixed);
  };
  // Enter loads, like the button. An Enter that confirms an IME candidate (isComposing / 229) must not.
  const onEnter = (e: { key: string; keyCode: number; nativeEvent: { isComposing: boolean } }) => {
    if (e.key === 'Enter' && !e.nativeEvent.isComposing && e.keyCode !== 229 && netlistReady) loadNetlist();
  };

  // Source "Virtuoso": libraries -> cells -> schematic follow each other without a button (user request 2026-09-20).
  // Each step starts from an explicit choice (the source, a library, a cell), waits for the step before it, and is a
  // gated, read-only, zero-cost bridge call. Refresh repeats the chain, e.g. after the link came up.
  const browsing = ref.source === 'virtuoso' && !!profileId;
  const nativeProblem = (step: string, e: any) => {
    const gate = e.detail?.gate, outdated = e.status === 404 || e.status === 405;
    setNativeError({ step, outdated, text: outdated ? 'This backend is older than the page and cannot do this yet: restart it (gator_workbench.cli serve).'
      : gate ? gateText(gate) : e.message });
  };
  const nativeStep = (step: string, call: () => Promise<Json>, done: (answer: Json) => void) => {
    let live = true;
    setListing(step); setNativeError(null);
    call().then(answer => { if (live) done(answer); })
      .catch((e: any) => { if (live) nativeProblem(step, e); })
      .finally(() => { if (live) setListing(current => (current === step ? null : current)); });
    return () => { live = false; setListing(current => (current === step ? null : current)); };
  };
  useEffect(() => {
    setLibraries(null);
    if (!browsing) return;
    return nativeStep('libraries', () => api.nativeLibraries(profileId!), answer => setLibraries(answer.libraries));
  }, [browsing, profileId, refresh]);
  useEffect(() => {
    setCells(null);
    if (!browsing || !libraries || !ref.library) return;
    return nativeStep('cells', () => api.nativeCells(profileId!, ref.library), answer => {
      setCells(answer);
      // The technology library a design library is attached to IS its PDK: offered as the label, never over a typed one.
      // An empty Testbench box takes the cell's `tb_<cell>`, as choosing the cell does - never over a chosen testbench.
      setConfig(c => {
        let circuit = c.circuit;
        if (answer.technology_library && (circuit.pdk_id ?? 'unspecified') === 'unspecified') circuit = { ...circuit, pdk_id: answer.technology_library };
        const named = !circuit.testbench_cell && circuit.library === answer.library ? namedTestbench(answer, circuit.cell) : null;
        if (named) circuit = { ...circuit, testbench_cell: named };
        return circuit === c.circuit ? c : { ...c, circuit };
      });
    });
  }, [browsing, profileId, libraries, ref.library]);
  const chosenCell = cells && cells.library === ref.library ? cells.cells.find((c: Json) => c.name === ref.cell) : null;
  useEffect(() => {                                   // Refresh reaches this step through the two above: the cell list comes back first
    setNative(null);
    if (!browsing || !chosenCell?.has_schematic) return;
    return nativeStep('schematic', () => api.nativeRead(profileId!, ref.library, ref.cell), setNative);
  }, [browsing, profileId, ref.library, ref.cell, !!chosenCell?.has_schematic]);
  // Reading a cell INTO the workbench is an explicit press: Virtuoso exports the netlist of the testbench (or of the cell)
  // and the sizes are read back - read-only, zero-cost, some seconds. The backend keeps the copy; the circuit then loads
  // from it like any other, so the editors, the validation and the agent can work on it. It still cannot run.
  // Save task (TaskSave.tsx, replaces Create profile - user decision 2026-09-21): the editors' rows become the task
  // real:<name>, which runs on the cell's working copy. After a first save or a Save as the form switches to the task; after
  // saving the open task again it is loaded again (its baseline may no longer hold).
  const [saved, setSaved] = useState<Json>(null);          // the last first save / Save as: said again once the task is open
  const taskSaved = (made: Json) => {
    setDeleted(null); setSaved(made.created ? made : null);
    api.tasks().then(t => setTasks(t.tasks)).catch(() => undefined);
    if (made.task_key === ref.task_id) { setConfig(c => ({ ...c, parameters: made.parameters })); load(ref); return; }
    setConfig(c => ({ ...c, parameters: made.parameters, circuit: { ...c.circuit, source: 'registered_task', task_id: made.task_key, circuit_class: made.circuit_class, pdk_id: made.pdk_id } }));
  };
  // A saved task: "Check now" runs the check Start runs by itself before every run (backend consistency.py - the editors,
  // the task file and the working copy in Virtuoso must agree; the run adapter connects and exports without simulating),
  // and after a finished Single baseline simulation its result is recorded as the task's reference. Both are explicit
  // presses; neither starts a simulation. A check result goes as soon as the rows change: it was about the rows before.
  const [taskCheck, setTaskCheck] = useState<Json>(null);
  const [profileBusy, setProfileBusy] = useState<string | null>(null);
  const [profileMessage, setProfileMessage] = useState<Json>(null);
  const generatedName = ref.source === 'registered_task' && circuit?.generated_profile ? String(ref.task_id ?? '').replace(/^real:/, '') : null;
  useEffect(() => { setTaskCheck(null); setProfileMessage(null); }, [generatedName]);
  useEffect(() => { setTaskCheck(null); }, [JSON.stringify([config.parameters, config.measurements, config.targets])]);
  const profileAction = async (what: string, action: () => Promise<void>) => {
    setProfileBusy(what); setProfileMessage(null);
    try { await action(); }
    catch (e: any) {
      const gate = e.detail?.gate;
      setProfileMessage({ level: 'error', text: e.status === 404 || e.status === 405 ? 'This backend is older than the page and cannot do this yet: restart it (gator_workbench.cli serve).'
        : gate ? gateText(gate) : e.message });
    } finally { setProfileBusy(null); }
  };
  const checkTask = () => profileAction('check', async () => { setTaskCheck(await api.taskCheck(profileId, config)); });
  const recordReference = () => profileAction('reference', async () => {
    const recorded = await api.profileReference(generatedName!);
    setProfileMessage({ level: 'ok', text: `Baseline recorded from run ${recorded.run_id ?? recorded.run_dir}. Every later run compares its first evaluation with it.` });
    await load(ref);
  });
  // Delete task: takes a saved task out of the list. Asked once more, because the task leaves the list. The backend keeps
  // the files aside and refuses while a run of the task is working. The form then goes back to the cell the task was saved
  // from, whose working copy is free again for a new task.
  const [deleted, setDeleted] = useState<Json>(null);
  const deleteProfile = () => {
    if (!window.confirm(`Delete the task real:${generatedName}?\n\nIt leaves the Registered task list, and its cell can get a new task. Runs already made `
      + 'with it keep their data, but a paused one can no longer be resumed. A copy of the task\'s files is kept on the backend machine, and its '
      + 'working copy stays in Virtuoso.'
      + (circuit?.baseline_recorded ? '\n\nIts recorded baseline goes with it: a new task needs a new real baseline simulation.' : ''))) return;
    profileAction('delete', async () => {
      const gone = await api.deleteProfile(generatedName!);
      setDeleted(gone);
      api.tasks().then(t => setTasks(t.tasks)).catch(() => undefined);
      setConfig(c => ({ ...c, circuit: { ...c.circuit, source: 'virtuoso', task_id: null, library: gone.library, cell: gone.cell, view: 'schematic', testbench_cell: gone.testbench_cell ?? null } }));
    });
  };
  const deletedHere = deleted && deleted.library === ref.library && deleted.cell === ref.cell ? deleted : null;
  const [importing, setImporting] = useState(false);
  const importCell = async () => {
    setImporting(true); setNativeError(null);
    try { await api.nativeImport(profileId!, ref.library, ref.cell, ref.testbench_cell ?? null); await load(ref, 'press'); }
    catch (e: any) { nativeProblem('import', e); }
    finally { setImporting(false); }
  };

  // Probes follow the testbench (user request 2026-09-21): a cell read THROUGH a testbench brings, in Probes, the results
  // of the circuit type that testbench fits, each naming the testbench net or supply branch it is read from
  // (profiles.testbench_probes - from the copy that was read, not from what the box shows now). Only after a choice of
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
      || (!!starter && sameJson(now.measurements, starter.measurements));
    if (!untouched) { setProbeNote({ state: 'kept', found }); return; }
    const staleTargets = !!starter && (now.targets ?? []).length > 0 && sameJson(now.targets, starter.targets);
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
  const namedHere = namedTestbench(cells, ref.cell);

  // Choosing a task brings THAT task's rows (user report 2026-09-21: real:gpdk045_ota5 still showed the MOCK fixture's
  // "score" as its only spec, and "synthetic-fixture" as its PDK). The labels follow at once. The rows of the three editors
  // are exchanged only while they are nobody's work - empty, or still exactly what the task before had brought; rows that
  // were edited stay, and the button offers the exchange. A project name nobody typed - the untouched default, or what some
  // task's starter gives (mock-opamp ...) - follows too, so a real run is not filed under mock_*; a typed name stays, on
  // the button as well. The exchange is not a history step of its own: one Undo takes back the task choice and everything
  // it brought.
  const [taskRows, setTaskRows] = useState<Json>(null);      // what the last task choice did to the editors: { task, state, ... }
  const following = useRef(0);                               // only the newest choice may answer
  const starterNamed = (p: Json) => (p.name === 'gator-project' && p.task_name === 'task')
    || tasks.some(t => t.starter_project?.name === p.name && t.starter_project?.task_name === p.task_name);
  const starterProblem = (e: any, taskId: string) => (e.status === 404 && taskId.startsWith('real:')
    ? 'This backend is older than the page and has no starting rows for a real task yet: restart it (gator_workbench.cli serve).' : e.message);
  const chooseTask = async (taskId: string, more: Json = {}) => {
    const before = config, mine = ++following.current;
    const listed = tasks.find(t => t.task_key === taskId);
    patch({ ...more, task_id: taskId, ...(listed?.circuit_class ? { circuit_class: listed.circuit_class } : {}), ...(listed?.pdk_id ? { pdk_id: listed.pdk_id } : {}) });
    setTaskRows({ task: taskId, state: 'reading' });
    const [previous, starter] = await Promise.all([
      before.circuit.task_id ? api.starter(before.circuit.task_id).catch(() => null) : null,
      api.starter(taskId).catch((e: any) => ({ problem: starterProblem(e, taskId) }))]);
    if (mine !== following.current) return;
    if (starter.problem) { setTaskRows({ task: taskId, state: 'unavailable', text: starter.problem }); return; }
    const untouched = noRows(before) || (!!previous && sameRows(before, previous));
    setConfig(c => (c.circuit.task_id !== taskId ? c : {
      ...c, project: starterNamed(c.project) ? { ...c.project, ...starter.project } : c.project,
      ...(untouched ? { parameters: starter.parameters, targets: starter.targets, measurements: starter.measurements } : {}) }), false);
    setTaskRows({ task: taskId, state: untouched ? 'brought' : 'kept', starter, from: before.circuit.task_id });
  };
  const useStarter = async () => {
    const taskId = ref.task_id;
    following.current++;
    try {
      const starter = await api.starter(taskId);
      setConfig(c => ({ ...c, ...starter, project: starterNamed(c.project) ? { ...c.project, ...starter.project } : c.project,
        run: { ...c.run, ...starter.run }, output: c.output, research: c.research }));
      setTaskRows({ task: taskId, state: 'brought', starter });
    } catch (e: any) { setError(starterProblem(e, taskId ?? '')); }
  };
  // A cell that already has a registered task - the profile made from it, or one of the verified built-in circuits -
  // gets no second profile: the note names the task. One short button, because it is about THIS cell (not a list of
  // tasks); it does what choosing the task under Source: Registered task does.
  const builtIn = circuit?.profile_task_generated === false;
  const taskNote = circuit?.profile_task && ref.source === 'virtuoso' ? (
    <div className="note">
      <p><b>This cell already has a registered task:</b> <code>{circuit.profile_task}</code>{builtIn ? ' (a verified built-in circuit)' : ''}{' '}
        <button onClick={() => chooseTask(circuit.profile_task, { source: 'registered_task' })} title="Source: Registered task, with this task chosen.">Open</button></p>
      <details className="more"><summary>What this means</summary>
        <p>The workbench can already optimize this cell - through that task, under Source: Registered task.{builtIn ? ' A verified built-in circuit gets no second task.'
          : ' Open it to change it (Save task) or to make another task from it (Save as), which gets a working copy of its own. To start over from the cell, open it and press Delete task.'}</p></details>
    </div>) : null;
  // What was read straight from Virtuoso. It is a line of the Hierarchy block; while no circuit is loaded (browse only)
  // there is no such block and it stands alone at the end of the panel.
  const nativeSchematic = native && (
    <details open={nativeOpen} onToggle={e => setNativeOpen(e.currentTarget.open)}><summary>Native schematic {native.library}/{native.cell} ({native.instance_count} instances, as read)</summary>
      <p className="warn">Requires confirmation: {native.requires_confirmation.join('; ')}</p>
      <table className="grid small"><tbody>{native.instances.map((i: Json) => <tr key={i.instance_path}><td>{i.instance_path}</td><td>{i.master.library}/{i.master.cell}</td>
        <td>{Object.entries(i.parameters).map(([k, v]: [string, any]) => `${k}=${v.raw}`).join('  ')}</td></tr>)}</tbody></table></details>);
  return (
    <section className="panel">
      <h3>Project</h3>
      <label>Name<input value={config.project.name} onChange={e => setConfig(c => ({ ...c, project: { ...c.project, name: e.target.value } }))} /></label>
      <label>Task name<input value={config.project.task_name} onChange={e => setConfig(c => ({ ...c, project: { ...c.project, task_name: e.target.value } }))} /></label>
      <h3>Circuit source</h3>
      <label>Source
        <select value={ref.source} onChange={e => patch({ source: e.target.value })}>
          <option value="registered_task">Registered task</option>
          <option value="netlist">Import Spectre netlist</option>
          <option value="virtuoso">Virtuoso library / cell / view</option>
        </select>
      </label>
      {ref.source === 'registered_task' && (<>
        <label>Task
          <select value={ref.task_id ?? ''} onChange={e => chooseTask(e.target.value)}>
            {tasks.map(t => <option key={t.task_key} value={t.task_key}>{t.task_key}{t.kind === 'mock' ? '  [MOCK]' : t.available ? '' : '  [blocked]'}</option>)}
          </select>
        </label>
        {ref.task_id && <button onClick={useStarter} title="Replaces the rows of Parameters, Probes and Specs with this task's own. A MOCK fixture: its declared groups and the toy score. A real circuit: the parameters its profile fixes and its targets of record. Everything stays editable, and Undo takes it back.">Load starter configuration</button>}
        {taskRows?.task === ref.task_id && (
          taskRows.state === 'reading' ? <p className="hint task-rows">Reading this task's rows...</p>
          : taskRows.state === 'unavailable' ? <p className="error task-rows">{taskRows.text}</p>
          : taskRows.state === 'kept' ? <p className="warn task-rows">Parameters, Probes and Specs still hold the rows you edited{taskRows.from ? <> for <code>{taskRows.from}</code></> : null}.
              <b> Load starter configuration</b> replaces them with this task's.</p>
          : sameRows(config, taskRows.starter) && <p className="hint task-rows">Parameters, Probes and Specs now show this task's rows
              {taskRows.starter.targets.length ? '' : ' - it has no targets of record, so Specs is yours to fill (its results are ready in Probes)'}. Undo brings the previous ones back.</p>)}
      </>)}
      {ref.source === 'netlist' && (<>
        <label title="Backend-side path inside an allowed input root. Not a browser upload folder.">Netlist path
          <input value={ref.netlist_path ?? ''} placeholder={`e.g. ${example.netlist_path}`} onKeyDown={onEnter} onChange={e => patch({ netlist_path: e.target.value })} /></label>
        <label title="Device/port mapping: port order and parameter semantics come from here, never guessed.">Device mapping (JSON)
          <input value={ref.parser_config_path ?? ''} placeholder={`e.g. ${example.parser_config_path}`} onKeyDown={onEnter} onChange={e => patch({ parser_config_path: e.target.value })} /></label>
        <div className="row">
          <button disabled={!netlistReady || loading} onClick={() => loadNetlist()} title="Reads and parses the two files on the backend machine. Nothing is simulated.">{loading ? 'Loading...' : 'Load netlist'}</button>
          <button disabled={loading} onClick={() => loadNetlist(example)} title="Fills in the project's small op-amp fixture and its mapping, and loads it.">Try the example</button>
        </div>
        {!netlistReady ? (<>
          <p className="hint">Two files are needed: fill in both paths, then press <b>Load netlist</b>.</p>
          <details className="more hint"><summary>Which two files, and where they may be</summary>
            <p>Both are read on the computer that runs the workbench - nothing is uploaded from the browser:</p>
            <ul className="steps-list">
              <li><b>Netlist path</b> - the Spectre netlist (.scs).</li>
              <li><b>Device mapping (JSON)</b> - says, for each device type in the netlist, which pin is which and what its parameters mean.
                The workbench never guesses this. The project's own mappings are in <code>configs/</code> (<code>configs/opamp.json</code>, <code>configs/gpdk045_opamp.json</code>, ...).</li>
            </ul>
            <p>Both must be inside {(meta?.allowed_input_roots ?? []).map((r: string) => <code key={r}>{r} </code>)}
              (another folder: start the backend with <code>--allow-input-root DIR</code>). A Windows path such as <code>D:\gator\my.scs</code> is
              converted for you.</p>
          </details>
        </>) : !circuit && !error && !loading && <p className="hint">Not loaded yet - press <b>Load netlist</b> (or Enter).</p>}
      </>)}
      {ref.source === 'virtuoso' && (<>
        {!profileId && <p className="hint">Press "Connection" above and choose a Virtuoso connection: the libraries are read from that Virtuoso.</p>}
        <label>Library
          <select value={ref.library ?? ''} disabled={!libraries} onChange={e => patch({ library: e.target.value || null, cell: null, view: null, testbench_cell: null }, true)}>
            <option value="">{listing === 'libraries' ? 'Reading the libraries...' : libraries ? `(choose one of ${libraries.length})` : '(not listed)'}</option>
            {withCurrent(libraries ?? [], ref.library).map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
        {nativeError?.outdated && nativeError.step === 'cells' ? (<>
          <label title="Typed, because this backend cannot list cells yet.">Cell<input value={ref.cell ?? ''} onChange={e => patch({ cell: e.target.value || null, view: 'schematic' })} /></label>
          <button disabled={!profileId || !ref.library || !ref.cell} onClick={() => { nativeStep('schematic', () => api.nativeRead(profileId!, ref.library, ref.cell), setNative); }}>Read native schematic</button>
        </>) : (<>
          <label title="Only a cell with a schematic view can be read.">Cell
            {/* A new cell takes its own tb_<cell>; without one, a testbench chosen by hand stays and the old cell's tb_ goes. */}
            <select value={ref.cell ?? ''} disabled={!cells} onChange={e => {
              const cell = e.target.value || null;
              patch({ cell, view: cell ? 'schematic' : null,
                testbench_cell: namedTestbench(cells, cell) ?? (ref.testbench_cell === namedHere ? null : ref.testbench_cell ?? null) }, true);
            }}>
              <option value="">{!ref.library ? '(choose a library first)' : listing === 'cells' ? 'Reading the cells...' : cells ? `(choose one of ${cells.cells.length})` : '(not listed)'}</option>
              {withCurrent((cells?.cells ?? []).map((c: Json) => c.name), ref.cell).map(name => {
                const readable = !cells || cells.cells.find((c: Json) => c.name === name)?.has_schematic !== false;
                return <option key={name} value={name} disabled={!readable}>{name}{readable ? '' : '  (no schematic view)'}</option>;
              })}
            </select>
          </label>
          {chosenCell && <details className="more hint"><summary>View: <b>schematic</b></summary>
            <p>The only view the reader opens, so there is nothing to choose.
              {chosenCell.views.length > 1 && ` This cell also has: ${chosenCell.views.filter((v: string) => v !== 'schematic').join(', ')}.`}</p></details>}
          <label title="The cell that holds the test setup around the design (supply, stimulus, load). Needed to create a profile, and Probes are read from it. A cell named tb_ + the cell's name is chosen by itself.">Testbench cell
            <select value={ref.testbench_cell ?? ''} disabled={!cells} onChange={e => patch({ testbench_cell: e.target.value || null }, true)}>
              <option value="">(none)</option>
              {withCurrent((cells?.cells ?? []).filter((c: Json) => c.has_schematic).map((c: Json) => c.name), ref.testbench_cell).map(name => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          {namedHere && ref.testbench_cell === namedHere && <p className="hint tb-named">Found by its name: <code>tb_</code> + the cell's name.</p>}
        </>)}
        <div className="row">
          <button disabled={!profileId || !!listing} onClick={() => setRefresh(n => n + 1)} title="Reads the libraries, the cells and the schematic again, e.g. after the link came up or the design changed in Virtuoso. Read-only and zero-cost.">Refresh</button>
          {listing && <span className="hint">Reading the {listing} from Virtuoso...</span>}
        </div>
        {cells?.truncated && <p className="hint">Only the first {cells.cells.length} cells are listed.</p>}
        {nativeError && <p className="error">{nativeError.text}</p>}
      </>)}
      <label title="A DUT may be identified inside one testbench; separate DUT/testbench files are not required.">DUT hierarchy / subcircuit<input value={ref.dut_hierarchy ?? ''} onChange={e => patch({ dut_hierarchy: e.target.value || null })} /></label>
      <div className="row">
        <label title="What kind of circuit this is: opamp, ldo, vco, ... A label for your records. Results tables are grouped by it, and the validator uses it to check a claim such as 'tested on an unseen circuit class'.">Circuit class
          <input list="circuit-classes" value={ref.circuit_class ?? ''} onChange={e => patch({ circuit_class: e.target.value || 'unspecified' })} />
          <datalist id="circuit-classes">{['opamp', 'ldo', 'vco', 'bandgap', 'comparator', 'oscillator', 'unspecified'].map(c => <option key={c} value={c} />)}</datalist></label>
        <label title="Which process design kit (technology) the circuit is built in, e.g. gpdk045. Written into the run records so a result can be traced to its technology. PDK files are never copied.">PDK id
          <input value={ref.pdk_id ?? ''} onChange={e => patch({ pdk_id: e.target.value || 'unspecified' })} /></label>
      </div>
      <details className="more hint"><summary>What circuit class and PDK id are for</summary>
        <p>Circuit class and PDK id are labels saved with every run. They do not change the simulation or the optimization;
          "unspecified" is fine for a single run.{ref.source === 'virtuoso' && ' The PDK id is filled in from the library\'s technology library.'}</p></details>
      {error && <p className="error">{error}</p>}
      {deletedHere && ref.source === 'virtuoso' && !circuit?.profile_task && (<>
        <p className="ok">Task <code>{deletedHere.deleted}</code> deleted. This cell can get a new one.</p>
        <details className="more hint"><summary>Where its files went</summary>
          <p>Nothing was erased. They are kept on the backend machine in <code>{deletedHere.kept_copy}</code>.</p></details>
      </>)}
      {circuit && ref.source === 'virtuoso' && taskNote}
      {circuit && !circuit.loaded && ref.source === 'virtuoso' && !taskNote && (
        // Not a fault and nothing to fix in this form: said in plain words. No list of the circuits that already have a
        // profile here (user, 2026-09-22): whoever wants one of those picks it under Source: Registered task.
        <div className="note">
          <p><b>Browse only: you can look at this cell here, but the workbench cannot optimize it yet.</b></p>
          <details className="more"><summary>Why: it has no <i>circuit profile</i> yet</summary>
            <p>To optimize a circuit in the real Virtuoso, the workbench needs a circuit profile - a checked description of three things:</p>
            <ul className="steps-list">
              <li>which device sizes it may change, within which limits and in which steps (Virtuoso rounds what is typed, so this is tested for each circuit);</li>
              <li>which testbench simulates the circuit, and under which conditions;</li>
              <li>how the results - gain, frequency, current ... - are read from the simulation.</li>
            </ul>
            <p>Circuits that already have one are under Source: Registered task.</p>
          </details>
          <p><b>To start a profile for this cell</b>, read it into the workbench
            {ref.testbench_cell ? <> through the testbench <code>{ref.testbench_cell}</code>.</> : <> (choose its <b>Testbench cell</b> above first, if it has one).</>}</p>
          <details className="more"><summary>What reading the cell does</summary>
            <p>Virtuoso exports the netlist and the device sizes are read. Read-only, no simulation, some seconds. The agent can then tell you
              what the circuit is and suggest what to vary.</p></details>
          <div className="row"><button className="primary" disabled={!profileId || !chosenCell?.has_schematic || importing || !!listing} onClick={importCell}>
            {importing ? 'Reading the cell from Virtuoso...' : 'Read this cell into the workbench'}</button></div>
          <details><summary>Technical details</summary><p>{circuit.blocker}</p>
            {circuit.interface_contract && <pre>{JSON.stringify(circuit.interface_contract, null, 1)}</pre>}</details>
        </div>)}
      {circuit && !circuit.loaded && ref.source !== 'virtuoso' && <div className="blocker"><b>Blocked:</b> {labelled(circuit.blocker ?? '')}
        {circuit.interface_contract && <details><summary>Interface contract</summary><pre>{JSON.stringify(circuit.interface_contract, null, 1)}</pre></details>}</div>}
      {circuit?.loaded && (<>
        {circuit.mock && <p className="mock">MOCK evaluation backend: {circuit.evaluation_backend}</p>}
        {circuit.mock === false && !circuit.native_draft && <p className="real">REAL evaluation backend: {circuit.evaluation_backend ?? 'Virtuoso + Spectre'}. Every
          evaluation is a costed simulation; Start asks you to authorize the budget first.</p>}
        {circuit.native_draft && !taskNote && (
          <div className="note">
            <p><b>Read from Virtuoso. Not optimizable yet: it has no circuit profile.</b></p>
            <details className="more"><summary>What you can do with it now</summary>
              <p>The workbench now holds its own copy of this cell, so you can look at it, fill the three editors and let the agent help.
                Start stays disabled.</p>
              <p>Next: make the working copy, then ask the agent to set it up - it says what the circuit is and proposes what to vary, what
                to measure (Maestro outputs, with their analyses) and specs. Its answer is a proposal in the Agent tab; once you approve it there,
                the three editors are filled and the setup is written into the working copy (never into your cell) and read back.</p>
            </details>
            {(circuit.circuit?.testbench_cell ?? null) !== (ref.testbench_cell ?? null) && (
              <p className="warn tb-stale">This copy was read {circuit.circuit?.testbench_cell ? <>through <code>{circuit.circuit.testbench_cell}</code></> : 'without a testbench'}.
                Press <b>Read the cell again</b> to read it {ref.testbench_cell ? <>through <code>{ref.testbench_cell}</code></> : 'without one'}: Probes then follow it.</p>)}
            <div className="row">
              <button className="primary" disabled={!circuit.working_copy?.verified} onClick={() => onAgent('virtuoso_setup', [], SETUP_PROMPT)}
                title={circuit.working_copy?.verified ? 'Opens the Agent tab with the request written out. Nothing is sent until you press Enter in its message box.' : 'Make the working copy first (below): the agent\'s setup is written into it.'}>Ask the agent to set up</button>
              <button disabled={!profileId || importing || !!listing} onClick={importCell} title="After a change in Virtuoso, or to export through another testbench cell. Read-only.">{importing ? 'Reading...' : 'Read the cell again'}</button>
            </div>
            <WorkingCopy profileId={profileId} library={ref.library} cell={ref.cell} testbench={circuit.circuit?.testbench_cell ?? null}
              record={circuit.working_copy} config={config} setConfig={setConfig} onCopied={() => load(ref)} />
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
            <p><b>Then save it as a task.</b></p>
            <TaskSave profileId={profileId} library={ref.library} cell={ref.cell} task={null} hasCopy={!!circuit.working_copy?.verified}
              config={config} setConfig={setConfig} onSaved={taskSaved} />
          </div>)}
        {circuit.generated_profile && !circuit.baseline_recorded && <p className="warn">This task has no real baseline yet: begin with
          <b> Single baseline simulation</b> (one real Spectre run, asks for your budget) before an optimization run.</p>}
        {saved && saved.task_key === ref.task_id && <p className="ok">Saved the new task <code>{saved.task_key}</code>. It runs on the working copy
          <code> {saved.copy?.library}/{saved.copy?.testbench}</code>; nothing has been simulated yet.</p>}
        {generatedName && (
          <div className="note">
            <TaskSave profileId={profileId} library={null} cell={null} task={generatedName}
              revision={tasks.find(t => t.task_key === ref.task_id)?.revision ?? null} hasCopy
              config={config} setConfig={setConfig} onSaved={taskSaved} />
            <p><b>Before every run:</b> Start, Single baseline simulation and Resume first check that the editors, this saved task and its
              working copy in Virtuoso agree. The check simulates nothing; a difference starts nothing and says what to do.</p>
            <details className="more"><summary>What the check compares</summary>
              <ul className="steps-list">
                <li>The rows of Parameters, Probes and Specs against the saved task. While you edit, the header's blocking issues say it too.</li>
                <li>The working copy against the task: the run adapter connects (no ADE/Maestro window may be open on the copy), Virtuoso exports
                  its netlist, the export is compared with the saved one - topology and every parameter - and the simulation deck is written.</li>
                <li>For a task measured by Maestro: the copy's Maestro test against the task.</li>
              </ul>
              <p>Everything but the rows needs the link up. Nothing is written into Virtuoso.</p></details>
            <div className="row">
              <button disabled={!!profileBusy} onClick={checkTask} title="The check Start runs by itself before every run. Read-only, no simulation.">
                {profileBusy === 'check' ? 'Checking...' : 'Check now'}</button>
              {!circuit.baseline_recorded && <button disabled={!!profileBusy} onClick={recordReference}
                title="After a finished Single baseline simulation of this task: its result becomes the reference that every later run is compared with. Recorded once, never replaced.">
                {profileBusy === 'reference' ? 'Recording...' : 'Record the baseline run as reference'}</button>}
            </div>
            {taskCheck && <CheckSteps result={taskCheck} />}
            {profileMessage && <p className={profileMessage.level === 'ok' ? 'ok' : 'error'}>{profileMessage.text}</p>}
            <div className="row start-over"><span className="hint">To start over from the cell:</span>
              <button disabled={!!profileBusy} onClick={deleteProfile} title="Asks once more. The task leaves the Registered task list; its files are kept aside, and runs already made keep their data.">
                {profileBusy === 'delete' ? 'Deleting...' : 'Delete task'}</button></div>
          </div>)}
        {circuit.notes?.length > 0 && <details className="more hint"><summary>{circuit.notes.length === 1 ? '1 note' : `${circuit.notes.length} notes`} on this circuit</summary>
          {circuit.notes.map((n: string) => <p key={n}>{n}</p>)}</details>}
        <details className="section" open={hierarchyOpen} onToggle={e => setHierarchyOpen(e.currentTarget.open)}>
          <summary><h3>Hierarchy ({circuit.summary.device_count} instances)</h3></summary>
          <Tree node={circuit.hierarchy} />
          <details><summary>Instances and parameters</summary>
            <table className="grid small"><thead><tr><th>Instance</th><th>Kind</th><th>Parameters (canonical units)</th></tr></thead>
              <tbody>{circuit.summary.devices.map((d: Json) => <tr key={d.instance_path}><td>{d.instance_path}</td><td>{d.kind}</td>
                <td>{Object.entries(d.parameters).map(([k, v]: [string, any]) => `${k}=${v.value ?? v.expression ?? '?'}`).join('  ')}</td></tr>)}</tbody></table>
          </details>
          {nativeSchematic}
        </details>
        {circuit.summary.unknown_devices.length > 0 && <p className="warn">Unmapped devices need confirmation: {circuit.summary.unknown_devices.join(', ')}</p>}
        {circuit.diagnostics.length > 0 && <details><summary>{circuit.diagnostics.length} diagnostics</summary><ul>{circuit.diagnostics.map((d: Json, i: number) => <li key={i} className={d.severity}>{d.code}: {d.message}</li>)}</ul></details>}
      </>)}
      {!circuit?.loaded && nativeSchematic}
    </section>
  );
}
