import { Fragment, ReactNode, useEffect, useRef, useState } from 'react';
import { api, gateText, Json, OLDER_BACKEND } from '../api';
import { kindUnit, si } from '../units';
import { plural, short } from '../format';
import { Icon } from './Icons';

export { gateText };

export const namedTestbench = (cells: Json, cell?: string | null): string | null => {
  if (!cells || !cell) return null;
  const found = (cells.cells ?? []).filter((c: Json) => c.has_schematic && /^tb_/i.test(c.name) && c.name.slice(3) === cell).map((c: Json) => c.name);
  return found.find((name: string) => name === `tb_${cell}`) ?? found[0] ?? null;
};

/** The read-only library → cell → schematic chain, active only while the Virtuoso window is open. */
export function useVirtuosoBrowser(enabled: boolean, profileId: string | null, chosen: Json, setConfig: (f: (c: Json) => Json, record?: boolean) => void) {
  const [native, setNative] = useState<Json>(null);
  // Each list remembers the connection it came from: right after another connection is chosen, the old lists no longer
  // count (the next steps used to ask the NEW connection about the old library list before it was cleared).
  const [listed, setListed] = useState<{ profile: string; list: string[] } | null>(null);
  const libraries = listed && listed.profile === profileId ? listed.list : null;   // null = not listed (yet)
  const [cellList, setCells] = useState<Json>(null);
  const cells: Json = cellList && cellList.profile === profileId ? cellList : null;   // { library, technology_library, cells: [{ name, views, has_schematic }] }
  const [listing, setListing] = useState<string | null>(null);            // what is being fetched from Virtuoso right now
  const [nativeError, setNativeError] = useState<string | null>(null);    // what the last failed step says
  // The words of the last refusal by the connection gate (branch record SIF-108): while the window shows them, its
  // Connection... button stands beside them. Whatever is said next - another failure, NO_TESTBENCH, nothing - takes it away.
  const [gateSaid, setGateSaid] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);                              // repeats the whole chain
  // The window: libraries -> cells -> schematic follow each other without a button (user request 2026-09-20). Each step
  // starts from an explicit choice (opening the window, a library, a cell), waits for the step before it, and is a
  // gated, read-only, zero-cost bridge call. Refresh repeats the chain, e.g. after the link came up.
  const browsing = enabled && !!profileId;
  // `then`: what to press once the link is up - Refresh after a step of the chain below, the read's own button again after a
  // read (Left.tsx importCell) - said beside the window's Connection... button (branch record SIF-108).
  const nativeProblem = (e: any, then = 'then try again') => {
    const gate = e.detail?.gate, outdated = e.status === 404 || e.status === 405 || (e.status === 422 && /work_here/.test(e.message ?? ''));
    const said = outdated ? OLDER_BACKEND : gate ? gateText(gate, then) : e.message;
    setNativeError(said); setGateSaid(gate && !outdated ? said : null);
  };
  const nativeStep = (step: string, call: () => Promise<Json>, done: (answer: Json) => void) => {
    let live = true;
    setListing(step); setNativeError(null);
    call().then(answer => { if (live) done(answer); })
      .catch((e: any) => { if (live) nativeProblem(e, 'then press Refresh'); })
      .finally(() => { if (live) setListing(current => (current === step ? null : current)); });
    return () => { live = false; setListing(current => (current === step ? null : current)); };
  };
  useEffect(() => {
    setListed(null);
    if (!browsing) return;
    return nativeStep('libraries', () => api.nativeLibraries(profileId!), answer => setListed({ profile: profileId!, list: answer.libraries }));
  }, [browsing, profileId, refresh]);
  useEffect(() => {
    setCells(null);
    if (!browsing || !libraries || !chosen.library) return;
    return nativeStep('cells', () => api.nativeCells(profileId!, chosen.library), answer => {
      setCells({ ...answer, profile: profileId });
      // The technology library a design library is attached to IS its PDK: offered as the label, never over a typed one.
      // An empty Testbench box takes the cell's `tb_<cell>`, as choosing the cell does - never over a chosen testbench.
      // Filled by itself, so no Undo step of its own: one Undo takes back the library choice and what it brought.
      setConfig(c => {
        let circuit = c.circuit;
        if (answer.technology_library && (circuit.pdk_id ?? 'unspecified') === 'unspecified') circuit = { ...circuit, pdk_id: answer.technology_library };
        const named = !circuit.testbench_cell && circuit.library === answer.library ? namedTestbench(answer, circuit.cell) : null;
        if (named) circuit = { ...circuit, testbench_cell: named };
        return circuit === c.circuit ? c : { ...c, circuit };
      }, false);
    });
  }, [browsing, profileId, libraries, chosen.library]);
  const chosenCell = cells && cells.library === chosen.library ? cells.cells.find((c: Json) => c.name === chosen.cell) : null;
  const readBefore = useRef(false);                   // a schematic was read in this window already
  useEffect(() => {                                   // Refresh reaches this step through the two above: the cell list comes back first
    setNative(null);
    if (!browsing) { readBefore.current = false; return; }
    if (!chosenCell?.has_schematic) return;
    // The first read in the window goes at once; another cell waits 0.4 s for the choice to settle: arrowing through the
    // Cell list chooses every cell on the way, and each read queued in the one Virtuoso session (answers to cells left
    // behind were dropped, but the reads still ran there).
    const wait = readBefore.current ? 400 : 0;
    readBefore.current = true;
    let stop: (() => void) | undefined;
    const timer = setTimeout(() => { stop = nativeStep('schematic', () => api.nativeRead(profileId!, chosen.library, chosen.cell), setNative); }, wait);
    return () => { clearTimeout(timer); stop?.(); };
  }, [browsing, profileId, chosen.library, chosen.cell, !!chosenCell?.has_schematic]);
  const nativeGated = !!nativeError && nativeError === gateSaid;
  return { native, libraries, cells, chosenCell, listing, nativeError, nativeGated, setNativeError, nativeProblem, setRefresh };
}

function Tree({ node, path = '' }: { node: Json; path?: string }) {
  const keys = Object.keys(node);
  if (!keys.length) return null;
  return <ul className="tree">{keys.map(k => <li key={path + k}><span>{k}</span><Tree node={node[k]} path={path + k + '/'} /></li>)}</ul>;
}

export function NativeSchematic({ native, open, setOpen }: { native: Json; open: boolean; setOpen: (v: boolean) => void }) {
  return native && (
    <details open={open} onToggle={e => setOpen(e.currentTarget.open)}><summary>Native schematic {native.library}/{native.cell} ({plural(native.instance_count, 'instance')}, as read)</summary>
      <p className="warn">Requires confirmation: {native.requires_confirmation.join('; ')}</p>
      <table className="grid small"><tbody>{native.instances.map((i: Json) => <tr key={i.instance_path}><td>{i.instance_path}</td><td>{i.master.library}/{i.master.cell}</td>
        <td>{Object.entries(i.parameters).map(([k, v]: [string, any]) => `${k}=${v.raw}`).join('  ')}</td></tr>)}</tbody></table></details>);
}

/** A size's value as the editors write it, "1.2 um" (branch record SIF-62, as record 7.208): the raw number read "w=0.0000012"
 *  under "Parameters (canonical units)". A parameter of no known kind keeps its plain number; one not resolved, its text. */
const sizeValue = (name: string, v: Json): string => typeof v.value === 'number' ? (kindUnit(name) ? si(v.value, kindUnit(name)) : short(v.value))
  : v.value ?? v.expression ?? '?';

/** "Add to Parameters" in the Instances table (branch record SIF-104), given by the circuit panel for a Virtuoso draft that Save
 *  as can make a task of: the Parameters rows as they are, and the press, which appends the row and gives its ID. */
export type SizeAdding = { rows: Json[]; add: (instance_path: string, parameter_name: string) => string };
/** Whether the sizes of the cell the page follows have "Add to Parameters", or will once it is read (branch record SIF-104): a
 *  cell read from Virtuoso that has no task yet. A cell with a task gets none (Left.tsx: its note names the task). The circuit
 *  panel gives the press by it, and the editors' empty Parameters line names the + by it, so the two cannot differ (review of
 *  SIF-104: the line named a + that a cell with a task does not have). */
export const sizesAddable = (config: Json, circuit: Json): boolean => config?.circuit?.source === 'virtuoso' && !circuit?.profile_task;

export function CircuitDetails({ circuit, open, setOpen, adding, children }: { circuit: Json; open: boolean; setOpen: (v: boolean) => void; adding?: SizeAdding;
  children: ReactNode }) {
  // The last size added here, named under the table while its row is there - Undo, a rename or Delete takes the line with the
  // row - and while this cell is the one shown.
  const [added, setAdded] = useState<{ cell: string; id: string; instance_path: string; name: string; text: string } | null>(null);
  if (!circuit?.loaded) return null;
  // The row each instance's parameter already is, by both (one look-up per size, not a search of the rows per size).
  const rowOf = new Map<string, string>((adding?.rows ?? []).map((r: Json) => [`${r.instance_path}\n${r.parameter_name}`, String(r.variable_id || '(no ID yet)')]));
  const line = added && added.cell === circuit.task_key && (adding?.rows ?? []).some((r: Json) => r.variable_id === added.id
    && r.instance_path === added.instance_path && r.parameter_name === added.name) ? added.text : null;
  return (<>
    {circuit.notes?.length > 0 && <details className="more hint"><summary>{circuit.notes.length === 1 ? '1 note' : `${circuit.notes.length} notes`} on this circuit</summary>
      {circuit.notes.map((n: string) => <p key={n}>{n}</p>)}</details>}
    <details className="section" open={open} onToggle={e => setOpen(e.currentTarget.open)}>
      <summary><h3>Hierarchy ({plural(circuit.summary.device_count, 'instance')})</h3></summary>
      <Tree node={circuit.hierarchy} />
      {/* Each size with a number has an "Add to Parameters" after it in a Virtuoso draft (branch record SIF-104): every row was
          typed by hand from this read-only table, in another window. The button is an icon, its words its label and tooltip,
          so the table reads as before; a size that is a row already has it off, naming the row. The row's Lower and Upper
          are left empty: validation marks it until they are typed, and Save as still takes only rows a real run can write.
          The present size is in the button's words and the line under the table, not in the row (Left.tsx). */}
      <details><summary>Instances and parameters</summary>
        <table className="grid small"><thead><tr><th>Instance</th><th>Kind</th><th>Parameters</th></tr></thead>
          <tbody>{circuit.summary.devices.map((d: Json) => <tr key={d.instance_path}><td>{d.instance_path}</td><td>{d.kind}</td>
            <td>{Object.entries(d.parameters).map(([k, v]: [string, any], i) => {
              const value = sizeValue(k, v), row = rowOf.get(`${d.instance_path}\n${k}`);
              return <Fragment key={k}>{i > 0 && ', '}<span className="size">{`${k} = ${value}`}{adding && typeof v.value === 'number'
                && <button className="add-size" aria-label="Add to Parameters" disabled={row !== undefined} onClick={() => {
                  const id = adding.add(d.instance_path, k);
                  setAdded({ cell: circuit.task_key, id, instance_path: d.instance_path, name: k,
                    text: `Added ${id} (${d.instance_path} ${k} = ${value}): type its Lower and Upper in Parameters, in the workbench.` });
                }} title={row !== undefined ? `Add to Parameters: ${d.instance_path} ${k} is already the Parameters row ${row}.`
                  : `Add to Parameters: A new row for ${d.instance_path} ${k} at the end of Parameters. Type its Lower and Upper there, a range `
                    + `that holds the present ${value}; the workbench's Undo takes it back.`}><Icon name="add" /></button>}</span></Fragment>;
            })}</td></tr>)}</tbody></table>
        {line && <p className="hint size-added" role="status">{line}</p>}
      </details>
      {children}
    </details>
    {circuit.summary.unknown_devices.length > 0 && <p className="warn">Unmapped devices need confirmation: {circuit.summary.unknown_devices.join(', ')}</p>}
    {/* The words first, the code on hover (branch record SIF-62, as SIF-52 in the ngspice window). */}
    {circuit.diagnostics.length > 0 && <details><summary>{plural(circuit.diagnostics.length, 'diagnostic')}</summary><ul>{circuit.diagnostics.map((d: Json, i: number) =>
      <li key={i} className={d.severity} title={`${d.severity}: ${d.code}`}>{d.message}</li>)}</ul></details>}
  </>);
}
