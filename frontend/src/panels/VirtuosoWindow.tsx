import type { ReactNode } from 'react';
import type { Json } from '../api';
import { namedTestbench } from './CircuitBrowser';
import { PdkWindowButton } from './Pdk';
import { WorkingCopy } from './WorkingCopy';

// The Virtuoso window (plan-refactoring C9, out of Left.tsx): library / cell / testbench, the read, the setup and what comes
// before the first save of a cell. The Project column's panel holds what it shows and does; CircuitPanelBody portals it into
// its pop-up window.

/** Why a first read cannot go without a testbench (branch record SIF-88): the backend refuses it before any export. Read
 *  is off until one is chosen, and importCell (Left.tsx) says it, before the copy question, should "Read the cell again"
 *  try a first read without one. */
export const NO_TESTBENCH = "Choose the cell's Testbench cell first: a task simulates the testbench and keeps its Maestro test there.";

/** A dropdown must be able to show the configured value even when the list does not (yet) contain it. */
const withCurrent = (names: string[], current?: string | null) => (current && !names.includes(current) ? [current, ...names] : names);

export function VirtuosoWindow({ profileId, virtuosoOn, offered, circuitRef: ref, chosen, libraries, cells, chosenCell, listing, importing, patch, setRefresh,
  pdkStep, nativeError, error, circuit, taskNote, importCell, config, setConfig, noteHere, takeTestbenchProbes, circuitInfo, nativeSchematic }: {
  profileId: string | null; virtuosoOn: boolean; offered: boolean; circuitRef: Json; chosen: Json; libraries: string[] | null; cells: Json; chosenCell: Json;
  listing: string | null; importing: boolean; patch: (fields: Json, follow?: 'choice' | 'press' | null) => void; setRefresh: (f: (n: number) => number) => void;
  pdkStep: Json; nativeError: string | null; error: string | null; circuit: Json; taskNote: ReactNode; importCell: () => void; config: Json;
  setConfig: (f: (c: Json) => Json, record?: boolean) => void; noteHere: Json; takeTestbenchProbes: () => void; circuitInfo: ReactNode;
  nativeSchematic: ReactNode }) {
  const namedHere = namedTestbench(cells, chosen.cell);
  const cellInfo = new Map<string, Json>((cells?.cells ?? []).map((c: Json) => [c.name, c]));   // one look-up per option, not a search
  const readable = !!profileId && !!chosenCell?.has_schematic && !importing && !listing;
  // The warning stays in view (never folded): the confirm repeats it once, when Read is pressed.
  const copyWarning = (
    <p className="warn copy-warning"><b>Work on a copy, never on your design.</b> The workbench makes no copy of its own: saving a task writes the
      Maestro test into the testbench, and every run sets device sizes in the cell (put back when the run ends). Copy the cell and its testbench
      in Virtuoso first, choose the copy above, and confirm when Read asks.</p>);
  return (
    <div className="virtuoso-window">
      <h2>Virtuoso cell</h2>
      <p className="hint">Read a cell from Virtuoso into the workbench, set it up and save it as a task. Choosing lists what Virtuoso has (read-only,
        no simulation); nothing is read on its own.</p>
      {!profileId && <p className="warn">Press "Connection" in the workbench and choose a Virtuoso connection: the libraries are read from that Virtuoso.</p>}
      {!virtuosoOn && offered && <p className="hint follows-task">The workbench follows the task <code>{ref.task_id}</code> now. Choosing a library here makes it follow the
        cell instead; the task is one choice away in the Tasks window.</p>}
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
            ? ` and ${pdkStep.ideal_parts.summary.recognized} ideal parts of ${pdkStep.ideal_parts.library}` : pdkStep.ideal_parts?.error ? `; the ideal parts of ${pdkStep.ideal_parts.library} were not read (${pdkStep.ideal_parts.error})` : ''}. To build the network with it, choose it under Components in the RL model window.</>
        : pdkStep.state === 'not_read' ? <>The cell was read; its PDK <b>{pdkStep.technology_library}</b> was not: {pdkStep.reason} "PDK window..." reads it by name.</>
        : <>No PDK read with the cell: {pdkStep.reason}</>}</p>}
      {cells?.truncated && <p className="hint">Only the first {cells.cells.length} cells are listed.</p>}
      {nativeError && <p className="error">{nativeError}</p>}
      {virtuosoOn && error && <p className="error">{error}</p>}
      {circuit && taskNote}
      {virtuosoOn && circuit && !circuit.loaded && !taskNote && (
        // Not a fault and nothing to fix in this form: said in plain words. No list of the circuits that already have a
        // task here (user, 2026-09-22): whoever wants one of those picks it in the Project column. What the cell lacks is
        // called a task, as Save as and the Tasks window call it (branch record SIF-61: it said "circuit profile", the word
        // of the "Create profile" button that went on 2026-09-22).
        <div className="note">
          <p><b>Browse only: you can look at this cell here, but the workbench cannot optimize it yet.</b></p>
          <details className="more"><summary>Why: it is not a task yet</summary>
            <p>To optimize a circuit in the real Virtuoso, the workbench needs a task - a checked description of three things:</p>
            <ul className="steps-list">
              <li>which device sizes it may change, within which limits and in which steps (Virtuoso rounds what is typed, so this is tested for each circuit);</li>
              <li>which testbench simulates the circuit, and under which conditions;</li>
              <li>how the results - gain, frequency, current ... - are read from the simulation.</li>
            </ul>
            <p>Circuits that already have one are in the Tasks window, under their task.</p>
          </details>
          {copyWarning}
          <p><b>To make a task of this cell</b>, read it into the workbench
            {chosen.testbench_cell ? <> through the testbench <code>{chosen.testbench_cell}</code>.</> : <> (choose its <b>Testbench cell</b> above first: a task needs one).</>}</p>
          <details className="more"><summary>What reading the cell does</summary>
            <p>Virtuoso exports the netlist and the device sizes are read. Read-only, no simulation, some seconds. Reading asks once whether
              the cell is a copy you made; "OK" makes it the cell the task flow works in.</p></details>
          <div className="row"><button className="primary" disabled={!readable || !chosen.testbench_cell} onClick={importCell}
            title={chosen.testbench_cell ? undefined : `Read this cell: ${NO_TESTBENCH}`}>
            {importing ? 'Reading the cell from Virtuoso...' : 'Read this cell into the workbench'}</button></div>
          <details><summary>Technical details</summary><p>{circuit.blocker}</p>
            {circuit.interface_contract && <pre>{JSON.stringify(circuit.interface_contract, null, 1)}</pre>}</details>
        </div>)}
      {virtuosoOn && circuit?.loaded && circuit.native_draft && !taskNote && (
        <div className="note">
          <p><b>Read from Virtuoso. Not optimizable yet: Save as makes it a task.</b></p>
          {/* The next step in view (branch record SIF-88): it was the second paragraph of the closed fold below, and a read
              leaves Parameters empty. It names the + of each size in the Hierarchy at the window's end (branch record SIF-104). */}
          <p className="hint next-step">Next: fill Parameters, Probes and Specs - the <b>+</b> after a size under <b>Hierarchy</b>, Instances and parameters
            (at the end of this window) adds it to Parameters, and <b>Read setup</b> below takes the outputs and specs of the cell's Maestro
            test - then press <b>Save as</b>: it writes the rows into this cell's Maestro view (the copy you declared) and reads it back.</p>
          <details className="more"><summary>What you can do with it now</summary>
            <p>The workbench holds the export of this cell, so you can look at it and fill the three editors. Start stays disabled. Claude Code
              or Codex (the Agent window: "Agent..." among the bottom tabs) can help with any of it, from what you describe.</p>
          </details>
          {/* A cell not yet declared is declared by its next read, which needs a testbench (importCell refuses it without one):
              the line asks for one instead of inviting that press (review of branch record SIF-88). */}
          {(circuit.circuit?.testbench_cell ?? null) !== (ref.testbench_cell ?? null) && (
            <p className="warn tb-stale">This cell was read {circuit.circuit?.testbench_cell ? <>through <code>{circuit.circuit.testbench_cell}</code></> : 'without a testbench'}.
              {ref.testbench_cell || circuit.working_copy?.verified
                ? <> Press <b>Read the cell again</b> to read it {ref.testbench_cell ? <>through <code>{ref.testbench_cell}</code></> : 'without one'}: Probes then follow it.</>
                : <> Choose its <b>Testbench cell</b> above to read it again: that read declares the cell the task flow works in, which needs one.</>}</p>)}
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
          <p><b>Then save it as a task:</b> <b>Save as</b> is above the editors in the workbench, next to their tabs.</p>
          <details className="more hint"><summary>What Save as does</summary>
            <p>It checks the rows, makes this cell's Maestro test say what the task says (its outputs, specs and analyses, read back afterwards),
              reads the cell into the workbench again and stores the task file with the task's files next to it, then runs one baseline simulation automatically. Save as
              asks for a new name with numbering. On a saved task it creates another task with its own DUT and testbench copies.</p></details>
        </div>)}
      {virtuosoOn && circuit?.loaded && circuitInfo}
      {!(virtuosoOn && circuit?.loaded) && nativeSchematic}
    </div>);
}
