import { useAsyncAction } from '../store';
import { MutableRefObject, useEffect, useRef, useState } from 'react';
import { api, Json, problemText } from '../api';
import { baselineText, followTaskBaseline } from './TaskSave';
import { usePopupWindow } from './popupWindow';
import { Blocked, PopupPortal } from './popupParts';
import { NGSPICE_WINDOW } from '../contract';

/** The ngspice window (user request 2026-09-23): a SPICE deck pasted or loaded from a file on the backend machine, checked,
 *  and saved as the task ngspice:<name> - one more entry of the Registered task list, which then runs on an ngspice
 *  connection (on this machine or over SSH; the Connection window). "From an ngspice netlist..." in the Tasks window opens it
 *  (record 7.362; until then ONE button in the Project column), and "ngspice netlist..." on the editors' tab line while the page
 *  follows such a task - the way the
 *  Virtuoso cell and the connection have their windows (a portal into a named pop-up). Opening the window runs nothing;
 *  Check reads the deck on the backend without storing it; Save stores it (the next revision when the name exists). */

const EXAMPLE = 'examples/circuits/ngspice_ota5_level1.cir';
const NAME = /^[a-z][a-z0-9_]{1,39}$/;
/** A Windows path typed on this machine, as the WSL backend sees it (D:\x\y.cir -> /mnt/d/x/y.cir). */
const backendPath = (text: string) => text.trim().replace(/^([A-Za-z]):[\\/]/, (_, d) => `/mnt/${d.toLowerCase()}/`).replace(/\\/g, '/');

/** `button` false (record 7.362): this keeps the window and its work, and the buttons that open it stand elsewhere - in the Tasks
 *  window and on the editors' tab line - calling `openRef.current(from)`; `onBlocked` tells them when the browser refused it. */
export function NgspiceButton({ config, circuit, chooseTask, onTasksChanged, button = true, openRef, onBlocked }:
  { config: Json; circuit: Json; chooseTask: (taskKey: string, labels?: { circuit_class?: string | null; pdk_id?: string | null }) => Promise<unknown> | void; onTasksChanged: () => void;
    button?: boolean; openRef?: MutableRefObject<((from?: Window | null) => void) | null>; onBlocked?: (blocked: boolean) => void }) {
  const ref = config.circuit;
  const followed: string | null = ref.source === 'registered_task' && /^ngspice:/.test(ref.task_id ?? '') ? ref.task_id.slice('ngspice:'.length) : null;
  // A Virtuoso connection hides this button (Left.tsx): the window closes with it instead of staying blank and orphaned.
  const { popup, root, blocked, open: openWindow } = usePopupWindow('gator-ngspice',
    { title: NGSPICE_WINDOW, features: 'popup,width=760,height=980', rootId: 'ngspice-root', closeOnUnmount: true });
  useEffect(() => { onBlocked?.(blocked); }, [blocked]);
  const [name, setName] = useState('');
  const [text, setText] = useState('');
  const [kinds, setKinds] = useState('');
  const [path, setPath] = useState('');
  const [sourcePath, setSourcePath] = useState<string | null>(null);   // where the deck was loaded from (relative includes resolve there)
  const [labels, setLabels] = useState({ circuit_class: 'unspecified', pdk_id: 'unspecified' });
  const [checked, setChecked] = useState<Json>(null);
  const [message, setMessage] = useState<Json>(null);             // { level: ok | error | hint, text }
  const [loadedFrom, setLoadedFrom] = useState<string | null>(null);  // the task whose deck the window holds
  const repo = useRef<string | null>(null);
  const problem = (e: any) => ({ level: 'error', text: problemText(e) });

  const { busy, run } = useAsyncAction(e => setMessage(problem(e)), () => setMessage(null));

  // The window holds the deck of the task the page follows (its saved text), read when it opens or the task changes.
  useEffect(() => {
    if (!popup) return;
    if (!followed) { if (loadedFrom) { setLoadedFrom(null); } return; }
    if (followed === loadedFrom) return;
    let live = true;
    api.ngspiceTask(followed).then(task => {
      if (!live) return;
      setLoadedFrom(followed); setName(task.name); setText(task.text); setSourcePath(task.source_path ?? null); setPath(task.source_path ?? '');
      setKinds(Object.entries(task.device_kinds ?? {}).map(([k, v]) => `${k}=${v}`).join(' '));
      setLabels({ circuit_class: task.circuit_class ?? 'unspecified', pdk_id: task.pdk_id ?? 'unspecified' });
      setChecked(null); setMessage({ level: 'hint', text: `Holding the saved deck of ngspice:${task.name} (revision ${task.revision}). Save stores the next revision.` });
    }).catch((e: any) => { if (live) setMessage(problem(e)); });
    return () => { live = false; };
  }, [popup, followed]);

  const load = (which: 'path' | 'example') => run('load', async () => {
    let target = backendPath(path);
    if (which === 'example') {
      if (!repo.current) repo.current = (await api.meta()).repo_root;
      target = `${repo.current}/${EXAMPLE}`;
    }
    const file = await api.ngspiceRead(target);
    setText(file.text); setSourcePath(file.path); setPath(file.path); setChecked(null);
    if (!name || (loadedFrom && name === loadedFrom && which === 'example')) setName(which === 'example' ? 'ota5_level1' : (file.path.split('/').pop() ?? '').replace(/\.[^.]*$/, '').toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/^[^a-z]+/, '') || 'netlist');
    setMessage({ level: 'ok', text: `Loaded ${file.path} (${file.size} bytes). Check it, then save it as a task.` });
  });
  const check = () => run('check', async () => { setChecked(await api.ngspiceCheck({ text, device_kinds: kinds, source_path: sourcePath })); });
  const save = () => run('save', async () => {
    const made = await api.ngspiceSave({ name, text, device_kinds: kinds, source_path: sourcePath, profile_id: config.run.connection_profile_id, output_root: config.output.output_root, ...labels });
    followTaskBaseline(made);
    setChecked(made.check ?? null); setLoadedFrom(made.name);
    onTasksChanged();
    await chooseTask(made.task_key, { circuit_class: made.circuit_class, pdk_id: made.pdk_id });   // a new task is not in the list read before
    setMessage({ level: made.baseline?.state === 'blocked' ? 'warn' : 'ok', text: `${made.created ? 'Saved the new task' : `Saved revision ${made.revision} of`} ${made.task_key}. The page follows it; `
      + 'Parameters and Probes show its rows (Specs are yours to fill). It runs on an ngspice connection: choose one in the Connection window.' + baselineText(made) });
  });
  const nameOk = NAME.test(name);
  const revision = followed && name === followed ? (circuit?.circuit?.revision ?? null) : null;

  const view = (
    <div className="virtuoso-window ngspice-window">
      <h2>ngspice netlist</h2>
      <p className="hint">Paste a SPICE deck, or load one from a file on the backend machine, and save it as a task. It then stands in the
        Registered task list as <code>ngspice:&lt;name&gt;</code> and runs on an ngspice connection (on this machine or over SSH:
        the Connection window). Opening this window runs nothing; Check reads the deck without keeping it.</p>
      <details className="more hint"><summary>What the deck must contain</summary>
        <ul className="steps-list">
          <li>The first line is the title. Then the elements, models (or <code>.include</code> / <code>.lib</code> lines), the analyses
            (<code>.op .ac .tran</code> ... or a <code>.control</code> block) and <code>.end</code>.</li>
          <li><b>Results</b>: <code>.meas</code> statements (<code>.meas ac gain_db max vdb(out)</code>), or in a <code>.control</code> block
            <code> meas ...</code> / <code>let x = ...</code> + <code>print x</code>. Their names become the Probes rows; a run reads
            the <code>name = value</code> lines ngspice prints. ngspice knows no <code>.meas op</code>: read operating-point values in a
            control block (<code>op</code>, <code>let</code>, <code>print</code>).</li>
          <li><b>Sizes a run can vary</b>: any numeric value of a top-level element (W, L, M, NF of a transistor; R, C, L, DC values),
            and of an element inside a subcircuit the deck uses exactly ONCE (a testbench around one DUT). A subcircuit used twice
            is shown, not sized. Parameters written as <code>{'{wn}'}</code> are replaced by the number for that run.</li>
          <li><b>Files</b>: on this machine, relative <code>.include</code> paths are resolved from the folder the deck was loaded from
            (a pasted deck has none: write absolute paths). Over SSH, every path in the deck is a path on that machine.</li>
          <li><b>Models the deck does not define</b> (a PDK cell as <code>X1 ... sky130_fd_pr__nfet_01v8</code>): declare their kind below,
            or they are shown as unknown and cannot be sized. ngspice simulates them either way.</li>
        </ul></details>
      <label>Task name<input value={name} onChange={e => setName(e.target.value.trim().toLowerCase())} placeholder="lowercase letters, digits, _"
        title="The task is registered as ngspice:<name>. An existing name is saved as its next revision." /></label>
      {followed && name === followed && <p className="hint">This is the task the page follows{revision ? ` (revision ${revision})` : ''}: Save stores its next revision.
        Runs made before keep their own copy of the deck.</p>}
      <div className="row ngspice-file">
        <label style={{ flex: '1 1 240px' }}>File on the backend machine<input value={path} onChange={e => setPath(e.target.value)} placeholder="/home/me/circuits/ota.cir or D:\circuits\ota.cir"
          onKeyDown={e => { if (e.key === 'Enter' && path.trim() && !busy) load('path'); }} title="Read by the backend, so the path is one on ITS machine (a Windows path is converted for the WSL backend). Only files under the allowed input roots can be read (--allow-input-root); paste the text otherwise." /></label>
        <button disabled={!!busy || !path.trim()} onClick={() => load('path')}>{busy === 'load' ? 'Loading...' : 'Load'}</button>
        <button disabled={!!busy} onClick={() => load('example')} title={`${EXAMPLE}: a five-transistor OTA on textbook level-1 models, with AC gain, unity-gain frequency and power measured. Free of any PDK.`}>Example</button>
      </div>
      {sourcePath && <p className="hint">Loaded from <code>{sourcePath}</code>: relative <code>.include</code> paths resolve from its folder on this machine.</p>}
      <label>Netlist<textarea className="ngspice-text" value={text} onChange={e => { setText(e.target.value); setChecked(null); }} rows={18} spellCheck={false}
        placeholder={'* title line\nvdd vdd 0 dc 1.8\n...\n.ac dec 20 1 1G\n.meas ac gain_db max vdb(out)\n.end'} /></label>
      <details className="more"><summary>Models the deck does not define: their kinds</summary>
        <label>name=kind pairs<input value={kinds} onChange={e => { setKinds(e.target.value); setChecked(null); }} placeholder="sky130_fd_pr__nfet_01v8=nmos sky130_fd_pr__pfet_01v8=pmos"
          title="Kinds: nmos, pmos, resistor, capacitor, inductor, vsource, isource. For subcircuits or models an included file defines." /></label></details>
      <details className="more"><summary>Labels: class <b>{labels.circuit_class}</b>, PDK <b>{labels.pdk_id}</b></summary>
        <div className="row">
          <label>Circuit class<input value={labels.circuit_class} onChange={e => setLabels(l => ({ ...l, circuit_class: e.target.value || 'unspecified' }))} /></label>
          <label>PDK id<input value={labels.pdk_id} onChange={e => setLabels(l => ({ ...l, pdk_id: e.target.value || 'unspecified' }))} /></label>
        </div>
        <p className="hint">Labels saved with the task and every run; they change nothing in the simulation.</p></details>
      <div className="row">
        <button disabled={!!busy || !text.trim()} onClick={check} title="Reads the deck on the backend: elements, what can be sized, the results it measures, problems. Stores and runs nothing.">
          {busy === 'check' ? 'Checking...' : 'Check'}</button>
        <button className="primary" disabled={!!busy || !text.trim() || !nameOk} onClick={save}
          title={nameOk ? 'Stores the deck as the task ngspice:<name> and makes the page follow it. A new task automatically runs one baseline simulation.' : 'Give the task a name first: lowercase letters, digits and _ (2-40 characters, starting with a letter).'}>
          {busy === 'save' ? 'Saving...' : followed && name === followed ? 'Save (next revision)' : 'Save as task'}</button>
        <p className="hint">Creating a task automatically runs one baseline simulation of its starting design.</p>
      </div>
      {message && <p className={message.level === 'ok' ? 'ok' : message.level === 'error' ? 'error' : 'hint'}>{message.text}</p>}
      {checked && (checked.ok === false ? <p className="error">Cannot read the deck: {checked.problem}</p> : (
        <div className="note ngspice-check">
          <p><b>{checked.title || '(no title line)'}</b>: {checked.devices} elements ({Object.entries(checked.kinds ?? {}).map(([k, n]) => `${n} ${k}`).join(', ')}),
            {' '}{checked.nets} nets, {checked.sizable.length} values a run can vary, {checked.measurements.length} results.</p>
          {checked.problems.length > 0 && <ul className="steps-list">{checked.problems.map((p: string) => <li key={p} className="warn">{p}</li>)}</ul>}
          {checked.measurements.length > 0 && <details className="more" open><summary>Results ({checked.measurements.length}): the Probes rows</summary>
            <table className="grid small"><thead><tr><th>Name</th><th>Analysis</th><th>Unit (a guess: edit the row)</th><th>Statement</th></tr></thead>
              <tbody>{checked.measurements.map((m: Json) => <tr key={m.name}><td>{m.name}</td><td>{m.analysis}</td><td>{m.unit}</td><td><code>{m.text}</code></td></tr>)}</tbody></table></details>}
          <details className="more"><summary>Values a run can vary ({checked.sizable.length})</summary><p>{checked.sizable.join(', ') || 'none'}</p></details>
          {checked.analyses.length > 0 && <details className="more"><summary>Analyses ({checked.analyses.length})</summary><p>{checked.analyses.map((a: string) => <code key={a}>{a} </code>)}</p></details>}
          {checked.unknown_models.length > 0 && <p className="warn">Shown as unknown (simulated, not sized): {checked.unknown_models.join(', ')}. Declare their kinds above to size them.</p>}
          {checked.includes.length > 0 && <p className="hint">Includes: {checked.includes.map((i: Json) => i.path).join(', ')}{sourcePath ? '' : ' - a pasted deck has no folder: relative paths must be absolute.'}</p>}
          {checked.diagnostics.length > 0 && <details className="more"><summary>{checked.diagnostics.length} diagnostics</summary>
            <ul>{checked.diagnostics.map((d: Json, i: number) => <li key={i} className={d.severity}>{d.code}: {d.message}</li>)}</ul></details>}
        </div>))}
    </div>);
  if (openRef) openRef.current = from => { openWindow(from ?? undefined); };
  return <>
    {button && <button className="ngspice-button" onClick={openWindow} title={popup ? 'The ngspice window is open: press to bring it to the front.'
      : 'Opens the ngspice window: paste or load a SPICE deck, check it and save it as a task that runs on an ngspice connection. Opening it runs nothing.'}>ngspice netlist...</button>}
    {button && blocked && <Blocked />}
    <PopupPortal popup={popup} root={root}>{view}</PopupPortal>
  </>;
}
