import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { BLOCKED, usePopupWindow } from './popupWindow';
import { api, Json } from '../api';

// Load PDK (user request 2026-09-21; backend src/gator_workbench/pdk.py). The RL network is BUILT from a list of the
// components it knows. The standard list is the optimizer's default (MOS, R, C, L, sources; anything else "unknown")
// and every model saved before this existed was trained with it. A loaded PDK gives a list with EVERY component of
// that PDK - its pins, its parameters and their scales, read from Virtuoso's own description of the technology library
// and from its Spectre model files. Choosing the list is a network setting like the encoder, so it lives in the RL
// network block; the window only loads and shows. Nothing happens on its own: a PDK is read only on "Load".

const FAMILY_NAME: Record<string, string> = { 'mos:n': 'n-MOS', 'mos:p': 'p-MOS', mos: 'MOS', 'bjt:npn': 'npn', 'bjt:pnp': 'pnp', bjt: 'bipolar',
  diode: 'diode', resistor: 'resistor', capacitor: 'capacitor', varactor: 'varactor', inductor: 'inductor', other: 'other' };
const FAMILY_ORDER = ['mos:n', 'mos:p', 'mos', 'bjt:npn', 'bjt:pnp', 'bjt', 'diode', 'resistor', 'capacitor', 'varactor', 'inductor', 'other'];
const byFamily = (summary: Json): string => FAMILY_ORDER.filter(k => summary?.by_family?.[k])
  .map(k => `${summary.by_family[k]} ${FAMILY_NAME[k]}${summary.by_family[k] > 1 && !k.startsWith('mos') && !k.startsWith('bjt') ? 's' : ''}`).join(', ');
const familyOf = (d: Json) => (d.family === 'mos' || d.family === 'bjt') && d.polarity ? `${d.family}:${d.polarity}` : d.family;
const loadedAt = (iso: string) => { const at = new Date(iso); return isNaN(+at) ? iso : at.toLocaleString(); };
const USABLE_PDK_ID = (id?: string | null) => !!id && /^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$/.test(id) && !['unspecified', 'synthetic-fixture'].includes(id);

/** The line of the RL network block: which components the network knows, and the button to the PDK window. */
export function ComponentList({ value, onChoose, profileId, circuitPdk }: { value: string; onChoose: (v: string) => void; profileId: string | null; circuitPdk?: string | null }) {
  const [list, setList] = useState<Json>(null);
  const [error, setError] = useState<string | null>(null);
  const { popup, root, blocked, open: openWindow } = usePopupWindow('gator-pdk',
    { title: 'GATOR - PDK', features: 'popup,width=1100,height=900', rootId: 'pdk-root' });
  const refresh = () => api.pdks().then(l => { setList(l); setError(null); }).catch(e => setError(e.status === 404
    ? 'This workbench server is older than the page: restart it to load PDKs.' : `The loaded PDKs cannot be listed: ${e.message}`));
  useEffect(() => { refresh(); }, []);                   // local files only: which PDKs were loaded before

  const pdks: Json[] = list?.pdks ?? [];
  const chosen: Json = pdks.find(p => p.vocabulary === value) ?? null;
  const missing = value !== 'standard' && list && !chosen;
  return (
    <div className="component-list">
      <div className="row component-row">
        <label title="Which components the RL network is built to know. A model trained with one list loads only with the same list.">Components
          <select value={value} onChange={e => onChoose(e.target.value)}>
            <option value="standard">{list?.standard?.label ?? 'standard (8 generic kinds)'}</option>
            {pdks.map(p => <option key={p.vocabulary} value={p.vocabulary}>{p.label}</option>)}
            {missing && <option value={value}>{`PDK ${value.slice(4)} (not loaded)`}</option>}
          </select></label>
        <button className="pdk-open" onClick={openWindow} title="Opens the PDK window: read a technology library's own description and its model files through the connection (read-only, no simulation), and see what was read.">Load PDK...</button>
      </div>
      <p className="hint component-what">{value === 'standard'
        ? <>Knows MOS, R, C, L and sources; other parts (bipolar, diodes, S-parameter blocks, ports) are "unknown" and stay fixed. Every model saved before PDK lists existed uses this list.</>
        : chosen ? <>Knows all {chosen.summary.devices} components of {chosen.pdk_id}: {byFamily(chosen.summary)}. Other parts keep their standard kinds.</>
        : null}</p>
      {missing && <p className="warn">PDK {value.slice(4)} is not loaded here. Load it with "Load PDK...", or choose another list.</p>}
      {blocked && <p className="error">{BLOCKED}</p>}
      {error && <p className="warn">{error}</p>}
      <details className="component-help"><summary>What the component list changes</summary>
        <p className="hint">The network turns every part of the circuit into a node with a kind, and every pin into a link with a role (drain,
          gate, collector...). It can only tell apart what its list names. With a PDK list, each PDK component has a kind of its own, its pins have
          their real roles, and all its numeric parameters reach the network, each on the scale the PDK declares. Its parameters can also be varied
          (lengths, counts, resistances, capacitances, inductances, voltages) - on the MOCK backend; a real circuit still writes only what its
          profile allows. The optimizer's own code is not changed: models saved before keep loading, and the M6 audit re-runs unchanged.</p></details>
      {popup && root && createPortal(<PdkWindow list={list} refresh={refresh} profileId={profileId} circuitPdk={circuitPdk} />, root)}
    </div>);
}

function PdkWindow({ list, refresh, profileId, circuitPdk }: { list: Json; refresh: () => Promise<void>; profileId: string | null; circuitPdk?: string | null }) {
  const [library, setLibrary] = useState(USABLE_PDK_ID(circuitPdk) ? String(circuitPdk) : '');
  const [modelFile, setModelFile] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState<Json>(null);
  const [showing, setShowing] = useState<string | null>(null);
  const pdks: Json[] = list?.pdks ?? [];
  const show = (id: string) => { setShowing(id); setError(null); api.pdk(id).then(setShown).catch(e => setError(e.message)); };
  const load = async () => {
    setBusy(true); setError(null);
    try {
      const loaded = await api.loadPdk(profileId!, library.trim() || null, modelFile.trim() || null);
      setShown(loaded); setShowing(loaded.pdk_id);
      await refresh();
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const libraryProblem = library.trim() && !/^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$/.test(library.trim()) ? 'A plain Cadence library name.' : null;
  const fileProblem = modelFile.trim() && !/^\/[A-Za-z0-9_./+\-]+$/.test(modelFile.trim()) ? 'An absolute path on the simulator host (letters, digits, / . _ - +).' : null;
  const devices: Json[] = (shown?.devices ?? []).slice().sort((a: Json, b: Json) =>
    FAMILY_ORDER.indexOf(familyOf(a)) - FAMILY_ORDER.indexOf(familyOf(b)) || a.model.localeCompare(b.model));
  return (
    <div className="pdk-window">
      <h2>Load PDK</h2>
      <p className="hint">Reads one technology library through the connection: Virtuoso's own description of every cell (pins, the parameters
        written to the netlist, their units) and the PDK's Spectre model files (what each device is). Read-only - no cellview is changed and nothing
        is simulated. The PDK files are not kept: only what the network needs, and the files' SHA-256.</p>
      <details><summary>What is read, and how it is decided</summary>
        <p className="hint">A cell's Spectre model, pin order and netlisted parameters come from its CDF. A cell that has none of its own (a
          resistor built from a primitive) is looked into: its schematic is opened read-only and closed again. Which kind of device a model is
          comes from the Spectre primitive it uses (bsim4, bjt, diode, resistor, capacitor, inductor), its polarity from the model's type, and each
          pin's role from the primitive terminal the pin reaches. A parameter's scale comes from its declared unit, else from the PDK's default
          value. Nothing is guessed from a name; what cannot be established is listed as "unknown".</p></details>
      <div className="row pdk-form">
        <label>Technology library<input value={library} placeholder="empty = the connection's design library's" onChange={e => setLibrary(e.target.value)} /></label>
        <label>Model file on the simulator host<input value={modelFile} placeholder="empty = the connection's model file" onChange={e => setModelFile(e.target.value)} /></label>
        <button className="pdk-load" disabled={busy || !profileId || !!libraryProblem || !!fileProblem} onClick={load}
          title="Read-only and zero-cost: one query of the library's description, and the model files downloaded, scanned and deleted.">{busy ? 'Reading...' : 'Load'}</button>
      </div>
      <p className="hint">Through connection <b>{profileId ?? '(none chosen)'}</b>.{busy ? ' Reading the description and the model files - usually well under a minute.' : ''}</p>
      {!profileId && <p className="warn">Choose a connection first: the "Connection" button in the left column.</p>}
      {(libraryProblem || fileProblem) && <p className="error">{libraryProblem ?? fileProblem}</p>}
      {error && <p className="error">{error}</p>}
      <h3>Loaded PDKs</h3>
      {pdks.length === 0 ? <p className="hint">None yet.</p> : <>
        <table className="grid small pdk-list"><thead><tr><th>PDK</th><th>Components</th><th>Loaded</th><th>Version</th></tr></thead><tbody>
          {pdks.map(p => <tr key={p.pdk_id} className={showing === p.pdk_id ? 'active' : undefined} onDoubleClick={() => show(p.pdk_id)} title="Double click to show what was read">
            <td>{p.pdk_id}</td><td>{p.summary.devices} ({byFamily(p.summary)})</td><td>{loadedAt(p.loaded_utc)}</td><td className="mono">{p.sha256.slice(0, 8)}</td></tr>)}
        </tbody></table>
        <p className="hint">Double click a row to show it. To use one, choose it under "Components" in the RL network block.</p></>}
      {shown && <PdkDetails pdk={shown} devices={devices} />}
    </div>);
}

function PdkDetails({ pdk, devices }: { pdk: Json; devices: Json[] }) {
  const files: Json[] = pdk.sources?.model_files ?? [];
  const troubled = devices.filter(d => d.problems?.length);
  return (
    <div className="pdk-details">
      <h3>{pdk.pdk_id}: {pdk.summary.devices} components</h3>
      <p className="hint">{byFamily(pdk.summary)}. Network: {pdk.kinds} kinds, {pdk.roles} pin roles, {pdk.columns} parameter columns (version <span className="mono">{pdk.version}</span>).
        {' '}Read from {pdk.summary.cells} cells and {files.length} model file{files.length === 1 ? '' : 's'}.</p>
      {troubled.length > 0 && <p className="warn">Not fully established: {troubled.map(d => `${d.model} (${d.problems.join('; ')})`).join(', ')}.</p>}
      <table className="grid small pdk-devices"><thead><tr><th>Kind</th><th>Spectre model</th><th>Cells</th><th>Pins</th><th>Parameters the network reads</th></tr></thead><tbody>
        {devices.map(d => <tr key={d.model} title={d.family_basis}>
          <td>{FAMILY_NAME[familyOf(d)] ?? d.family}</td><td className="mono">{d.model}</td><td>{d.cells.join(', ')}</td>
          <td>{d.pins.map((p: Json) => `${p.name} ${p.role}`).join(', ')}</td>
          <td>{d.parameters.filter((p: Json) => p.numeric).map((p: Json) =>
            `${p.name}${p.column !== p.name ? ` = ${p.column}` : ''}${p.unit ? ` (${p.unit})` : ''}`).join(', ')}</td></tr>)}
      </tbody></table>
      <p className="hint">Hover a row for how its kind was decided. "(m)", "(F)"...: the unit the PDK declares (or the standard parameter of the same name
        and scale); a parameter without a unit can still be varied when its Parameters row states one.</p>
      <details><summary>Cells that are not components ({(pdk.not_netlisted?.length ?? 0) + (pdk.layout_only?.length ?? 0)})</summary>
        <ul className="hint">{(pdk.not_netlisted ?? []).map((c: Json) => <li key={c.cell}>{c.cell}: {c.reason}</li>)}
          {(pdk.layout_only ?? []).map((c: Json) => <li key={c.cell}>{c.cell}: layout only</li>)}</ul></details>
      {(pdk.not_used ?? []).length > 0 && <details><summary>In the model files but placed by no cell ({pdk.not_used.length})</summary>
        <p className="hint mono">{pdk.not_used.join(', ')}</p></details>}
      <details><summary>Model files read</summary>
        <table className="grid small"><tbody>{files.map((f: Json) => <tr key={f.path}><td className="mono">{f.path}</td><td className="numeric">{f.bytes} bytes</td><td className="mono">{String(f.sha256).slice(0, 16)}</td></tr>)}</tbody></table></details>
    </div>);
}
