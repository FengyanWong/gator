import { ReactNode, useEffect, useState } from 'react';
import { api, Json, OLDER_BACKEND } from '../api';

export const gateText = (gate: Json) => gate.blocking?.includes('connection_kind') ? (gate.next_steps?.[0] ?? 'This kind of connection cannot do that.')
  : `Virtuoso cannot be reached (${[...(gate.blocking ?? []), ...(gate.uncertain ?? [])].join(', ') || gate.status}). Bring the link up in the Connection window (the "Connection" button in the workbench), then try again.`;

export const namedTestbench = (cells: Json, cell?: string | null): string | null => {
  if (!cells || !cell) return null;
  const found = (cells.cells ?? []).filter((c: Json) => c.has_schematic && /^tb_/i.test(c.name) && c.name.slice(3) === cell).map((c: Json) => c.name);
  return found.find((name: string) => name === `tb_${cell}`) ?? found[0] ?? null;
};

/** The read-only library → cell → schematic chain, active only while the Virtuoso window is open. */
export function useVirtuosoBrowser(enabled: boolean, profileId: string | null, chosen: Json, setConfig: (f: (c: Json) => Json) => void) {
  const [native, setNative] = useState<Json>(null);
  const [libraries, setLibraries] = useState<string[] | null>(null);      // null = not listed (yet)
  const [cells, setCells] = useState<Json>(null);                         // { library, technology_library, cells: [{ name, views, has_schematic }] }
  const [listing, setListing] = useState<string | null>(null);            // what is being fetched from Virtuoso right now
  const [nativeError, setNativeError] = useState<Json>(null);             // { step, text, outdated }
  const [refresh, setRefresh] = useState(0);                              // repeats the whole chain
  // The window: libraries -> cells -> schematic follow each other without a button (user request 2026-09-20). Each step
  // starts from an explicit choice (opening the window, a library, a cell), waits for the step before it, and is a
  // gated, read-only, zero-cost bridge call. Refresh repeats the chain, e.g. after the link came up.
  const browsing = enabled && !!profileId;
  const nativeProblem = (step: string, e: any) => {
    const gate = e.detail?.gate, outdated = e.status === 404 || e.status === 405 || (e.status === 422 && /work_here/.test(e.message ?? ''));
    setNativeError({ step, outdated, text: outdated ? OLDER_BACKEND
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
    if (!browsing || !libraries || !chosen.library) return;
    return nativeStep('cells', () => api.nativeCells(profileId!, chosen.library), answer => {
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
  }, [browsing, profileId, libraries, chosen.library]);
  const chosenCell = cells && cells.library === chosen.library ? cells.cells.find((c: Json) => c.name === chosen.cell) : null;
  useEffect(() => {                                   // Refresh reaches this step through the two above: the cell list comes back first
    setNative(null);
    if (!browsing || !chosenCell?.has_schematic) return;
    return nativeStep('schematic', () => api.nativeRead(profileId!, chosen.library, chosen.cell), setNative);
  }, [browsing, profileId, chosen.library, chosen.cell, !!chosenCell?.has_schematic]);
  return { native, libraries, cells, chosenCell, listing, nativeError, setNativeError, nativeProblem, setRefresh };
}

function Tree({ node, path = '' }: { node: Json; path?: string }) {
  const keys = Object.keys(node);
  if (!keys.length) return null;
  return <ul className="tree">{keys.map(k => <li key={path + k}><span>{k}</span><Tree node={node[k]} path={path + k + '/'} /></li>)}</ul>;
}

export function NativeSchematic({ native, open, setOpen }: { native: Json; open: boolean; setOpen: (v: boolean) => void }) {
  return native && (
    <details open={open} onToggle={e => setOpen(e.currentTarget.open)}><summary>Native schematic {native.library}/{native.cell} ({native.instance_count} instances, as read)</summary>
      <p className="warn">Requires confirmation: {native.requires_confirmation.join('; ')}</p>
      <table className="grid small"><tbody>{native.instances.map((i: Json) => <tr key={i.instance_path}><td>{i.instance_path}</td><td>{i.master.library}/{i.master.cell}</td>
        <td>{Object.entries(i.parameters).map(([k, v]: [string, any]) => `${k}=${v.raw}`).join('  ')}</td></tr>)}</tbody></table></details>);
}

export function CircuitDetails({ circuit, open, setOpen, children }: { circuit: Json; open: boolean; setOpen: (v: boolean) => void; children: ReactNode }) {
  return circuit?.loaded && (<>
    {circuit.notes?.length > 0 && <details className="more hint"><summary>{circuit.notes.length === 1 ? '1 note' : `${circuit.notes.length} notes`} on this circuit</summary>
      {circuit.notes.map((n: string) => <p key={n}>{n}</p>)}</details>}
    <details className="section" open={open} onToggle={e => setOpen(e.currentTarget.open)}>
      <summary><h3>Hierarchy ({circuit.summary.device_count} instances)</h3></summary>
      <Tree node={circuit.hierarchy} />
      <details><summary>Instances and parameters</summary>
        <table className="grid small"><thead><tr><th>Instance</th><th>Kind</th><th>Parameters (canonical units)</th></tr></thead>
          <tbody>{circuit.summary.devices.map((d: Json) => <tr key={d.instance_path}><td>{d.instance_path}</td><td>{d.kind}</td>
            <td>{Object.entries(d.parameters).map(([k, v]: [string, any]) => `${k}=${v.value ?? v.expression ?? '?'}`).join('  ')}</td></tr>)}</tbody></table>
      </details>
      {children}
    </details>
    {circuit.summary.unknown_devices.length > 0 && <p className="warn">Unmapped devices need confirmation: {circuit.summary.unknown_devices.join(', ')}</p>}
    {circuit.diagnostics.length > 0 && <details><summary>{circuit.diagnostics.length} diagnostics</summary><ul>{circuit.diagnostics.map((d: Json, i: number) => <li key={i} className={d.severity}>{d.code}: {d.message}</li>)}</ul></details>}
  </>);
}
