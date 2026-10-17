import { useAsyncAction } from '../store';
import { useEffect, useMemo, useState } from 'react';
import { usePopupWindow } from './popupWindow';
import { Blocked, PopupPortal } from './popupParts';
import { signal } from '../signal';
import { dateTimeOrText as loadedAt } from '../format';
import { PDK_WINDOW } from '../contract';
import { api, gateText, Json, problemText } from '../api';
import { useNewest } from '../newest';

// Load PDK (user request 2026-09-21; backend src/gator_workbench/pdk.py). The RL network is BUILT from a list of the
// components it knows. The standard list is the optimizer's default (MOS, R, C, L, sources; anything else "unknown")
// and every model saved before this existed was trained with it. A loaded PDK gives a list with EVERY component of
// that PDK - its pins, its parameters and their scales, read from Virtuoso's own description of the technology library
// and from its Spectre model files. Choosing the list is a network setting like the encoder, so it lives in the RL
// model window, with the network. LOADING is the Virtuoso window's work since 2026-09-27 (user:
// "when loading a schematic from Virtuoso, shouldn't the PDK be loaded at the same time?"): reading a cell into the
// workbench reads its PDK in the same press (backend bridge_read.pdk_with_import), and that window's "PDK window..."
// button opens this file's window to read one by name and to see what was read. Nothing is read on its own.
// Since record 7.190 every read of a PDK also brings the ideal parts of analogLib (sources, ideal R / C / L, probes,
// controlled sources; backend pdk.build_ideal_parts): what a circuit holds besides its PDK's components is recognized from
// Virtuoso's own description too (user, 2026-10-05: "it should be recognizing all the loaded components").

const FAMILY_NAME: Record<string, string> = { 'mos:n': 'n-MOS', 'mos:p': 'p-MOS', mos: 'MOS', 'bjt:npn': 'npn', 'bjt:pnp': 'pnp', bjt: 'bipolar',
  diode: 'diode', resistor: 'resistor', capacitor: 'capacitor', varactor: 'varactor', inductor: 'inductor', other: 'other' };
const FAMILY_ORDER = ['mos:n', 'mos:p', 'mos', 'bjt:npn', 'bjt:pnp', 'bjt', 'diode', 'resistor', 'capacitor', 'varactor', 'inductor', 'other'];
const byFamily = (summary: Json): string => FAMILY_ORDER.filter(k => summary?.by_family?.[k])
  .map(k => `${summary.by_family[k]} ${FAMILY_NAME[k]}${summary.by_family[k] > 1 && !k.startsWith('mos') && !k.startsWith('bjt') ? 's' : ''}`).join(', ');
const familyOf = (d: Json) => (d.family === 'mos' || d.family === 'bjt') && d.polarity ? `${d.family}:${d.polarity}` : d.family;
const USABLE_PDK_ID = (id?: string | null) => !!id && /^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$/.test(id) && !['unspecified', 'synthetic-fixture'].includes(id);

// "The loaded PDKs changed" (a cell read in the Virtuoso window brought one, a Load in the PDK window): every Components
// list on the page reads the local list again - one GET each, no timer.
const watchers = signal(null);
export function pdksChanged() { watchers.notify(); }
const listProblem = (e: any) => e.status === 404 ? 'This workbench server is older than the page: restart it to load PDKs.' : `The loaded PDKs cannot be listed: ${e.message}`;

/** The loaded PDKs (local files only), read while `watch` is set - a list on the page, an open window - and again
 *  whenever they change. */
function usePdkList(watch: unknown) {
  const [list, setList] = useState<Json>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => api.pdks().then(l => { setList(l); setError(null); }).catch(e => setError(listProblem(e)));
  useEffect(() => {
    if (!watch) return undefined;
    refresh();
    return watchers.subscribe(refresh);
  }, [watch]);
  return { list, error };
}

/** The Components line of the RL model window: which components the network knows. It only chooses; reading a PDK is the
 *  Virtuoso window's. */
export function ComponentList({ value, onChoose }: { value: string; onChoose: (v: string) => void }) {
  const { list, error } = usePdkList(true);
  const pdks: Json[] = list?.pdks ?? [];
  const chosen: Json = pdks.find(p => p.vocabulary === value) ?? null;
  const missing = value.startsWith('pdk:') && list && !chosen;
  return (
    <div className="component-list">
      <div className="row component-row">
        <label title="Which components the RL network is built to know. A model trained with one list loads only with the same list, and a parameter outside the eight standard ones can be varied only with a PDK list.">Components
          <select value={value} onChange={e => onChoose(e.target.value)}>
            <option value="families">Device families (any PDK)</option>
            {pdks.map(p => <option key={p.vocabulary} value={p.vocabulary}>{p.label}</option>)}
            {value === 'standard' && <option value="standard">Standard (8 generic kinds) - kept for older models</option>}
            {missing && <option value={value}>{`PDK ${value.slice(4)} (not loaded)`}</option>}
          </select></label>
      </div>
      <p className="hint component-what">{value === 'families'
        ? <>Knows the device families of any PDK: nMOS, pMOS, npn, pnp, diode, varactor, resistor, capacitor, inductor and sources. Each part of the task's PDK takes its family by rule (its bipolars, diodes and varactors once the PDK is loaded); a model trained with this list loads with any PDK. The list of a new model since record 7.298. A PDK's own list appears here once the PDK was read: reading a cell in the Virtuoso window reads its PDK too.</>
        : value === 'standard'
        ? <>Knows MOS, R, C, L and sources; other parts are "unknown". Kept to continue the models trained with it: a new model uses the device families. A PDK's own list appears here once the PDK was read: reading a cell in the Virtuoso window reads its PDK too.</>
        : chosen ? <>Knows all {chosen.summary.devices} components of {chosen.pdk_id}: {byFamily(chosen.summary)}. Other parts keep their standard kinds. A model trained with this list loads only with it.</>
        : null}</p>
      {missing && <p className="warn">PDK {value.slice(4)} is not loaded here. Read it in the Virtuoso window (reading a cell reads its PDK; "PDK window..." reads one by name), or choose another list.</p>}
      {error && <p className="warn">{error}</p>}
      <details className="component-help"><summary>What the component list changes</summary>
        <p className="hint">The network turns every part of the circuit into a node with a kind, and every pin into a link with a role (drain,
          gate, collector...). It can only tell apart what its list names. With a PDK list, each PDK component has a kind of its own, its pins have
          their real roles, and all its numeric parameters reach the network, each on the scale the PDK declares. Its parameters can also be varied
          (lengths, counts, resistances, capacitances, inductances, voltages) - on the MOCK backend; a real circuit still writes only what its
          profile allows. Two consequences: a model trained with one list loads only with that list, and a Parameters row on a parameter outside the
          eight standard ones (w, l, m, nf, r, c, ind, dc) can run only with a PDK list - validation says so at the row. The optimizer's own code is
          not changed by a list.</p></details>
    </div>);
}

/** The button to the PDK window, in the Virtuoso window: read one PDK by name through the connection, see what was read. */
export function PdkWindowButton({ profileId, circuitPdk }: { profileId: string | null; circuitPdk?: string | null }) {
  // The button lives in the Virtuoso window: when that window closes, this one closes with it - it would stay blank,
  // with nothing left to draw it.
  const { popup, root, blocked, open: openWindow } = usePopupWindow('gator-pdk',
    { title: PDK_WINDOW, features: 'popup,width=1100,height=900', rootId: 'pdk-root', closeOnUnmount: true });
  const { list, error } = usePdkList(popup);
  return (<>
    <button className="pdk-open" onClick={e => openWindow(e.currentTarget.ownerDocument.defaultView)} title="Opens the PDK window: read one technology library by name through the connection (read-only, no simulation) and see what was read. Reading a cell into the workbench reads its PDK by itself.">PDK window...</button>
    {blocked && <Blocked as="span" />}
    <PopupPortal popup={popup} root={root}><PdkWindow list={list} listError={error} profileId={profileId} circuitPdk={circuitPdk} /></PopupPortal>
  </>);
}

function PdkWindow({ list, listError, profileId, circuitPdk }: { list: Json; listError: string | null; profileId: string | null; circuitPdk?: string | null }) {
  const [library, setLibrary] = useState(USABLE_PDK_ID(circuitPdk) ? String(circuitPdk) : '');
  const [modelFile, setModelFile] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState<Json>(null);
  const [showing, setShowing] = useState<string | null>(null);
  const pdks: Json[] = list?.pdks ?? [];
  // Only the newest row asked answers: a double click on A and then B showed the slower of the two under B.
  const asked = useNewest();
  const show = (id: string) => { const mine = asked.next(); setShowing(id); setError(null);
    api.pdk(id).then(v => { if (mine()) setShown(v); }, e => { if (mine()) setError(problemText(e)); }); };
  const { busy, run } = useAsyncAction(e => setError(problemText(e, gateText)), () => setError(null));
  const load = () => run('load', async () => {
      const loaded = await api.loadPdk(profileId!, library.trim() || null, modelFile.trim() || null);
      asked.drop(); setShown(loaded); setShowing(loaded.pdk_id);
      pdksChanged();              // every open list reads again - this window's too - and the RL model window's Components list shows it at once
  });
  const libraryProblem = library.trim() && !/^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$/.test(library.trim()) ? 'A plain Cadence library name.' : null;
  const fileProblem = modelFile.trim() && !/^\/[A-Za-z0-9_./+\-]+$/.test(modelFile.trim()) ? 'An absolute path on the simulator host (letters, digits, / . _ - +).' : null;
  const devices: Json[] = useMemo(() => (shown?.devices ?? []).slice().sort((a: Json, b: Json) =>
    FAMILY_ORDER.indexOf(familyOf(a)) - FAMILY_ORDER.indexOf(familyOf(b)) || a.model.localeCompare(b.model)), [shown]);   // sorted once per PDK shown, not per redraw
  return (
    <div className="pdk-window">
      <h2>Load PDK</h2>
      <p className="hint">Reads one technology library through the connection: Virtuoso's own description of every cell (pins, the parameters
        written to the netlist, their units) and the PDK's Spectre model files (what each device is). Read-only - no cellview is changed and nothing
        is simulated. The PDK files are not kept: only what the network needs, and the files' SHA-256. Reading a cell into the workbench reads
        its PDK by itself (since 2026-09-27); this window reads one again, or another one by name. Each read also brings the ideal parts
        of analogLib - sources, ideal R, C and L, probes, controlled sources - which a circuit holds besides its PDK's components.</p>
      <details><summary>What is read, and how it is decided</summary>
        <p className="hint">A cell's Spectre model, pin order and netlisted parameters come from its CDF. A cell that has none of its own (a
          resistor built from a primitive) is looked into: its schematic is opened read-only and closed again. Which kind of device a model is
          comes from the Spectre primitive it uses (bsim4, bjt, diode, resistor, capacitor, inductor), its polarity from the model's type, and each
          pin's role from the primitive terminal the pin reaches. A parameter's scale comes from its declared unit, else from the PDK's default
          value. Nothing is guessed from a name; what cannot be established is listed as "unknown".</p></details>
      <div className="row pdk-form">
        <label>Technology library<input value={library} placeholder="empty = the connection's design library's" onChange={e => setLibrary(e.target.value)} /></label>
        <label>Model file on the simulator host<input value={modelFile} placeholder="empty = the connection's model file" onChange={e => setModelFile(e.target.value)} /></label>
        <button className="pdk-load" disabled={!!busy || !profileId || !!libraryProblem || !!fileProblem} onClick={load}
          title="Read-only and zero-cost: one query of the library's description, and the model files downloaded, scanned and deleted.">{busy ? 'Reading...' : 'Load'}</button>
      </div>
      <p className="hint">Through connection <b>{profileId ?? '(none chosen)'}</b>.{busy ? ' Reading the description and the model files - usually well under a minute.' : ''}</p>
      {!profileId && <p className="warn">Choose a connection first: the "Connection" button in the header.</p>}
      {(libraryProblem || fileProblem) && <p className="error">{libraryProblem ?? fileProblem}</p>}
      {error && <p className="error">{error}</p>}
      {listError && <p className="warn">{listError}</p>}
      <h3>Loaded PDKs</h3>
      {pdks.length === 0 ? <p className="hint">None yet.</p> : <>
        <table className="grid small pdk-list"><thead><tr><th>PDK</th><th>Components</th><th title="The ideal parts of analogLib read with it: sources, ideal R, C and L, probes, controlled sources">Ideal parts</th><th>Loaded</th><th>Version</th></tr></thead><tbody>
          {pdks.map(p => <tr key={p.pdk_id} className={showing === p.pdk_id ? 'active' : undefined} onDoubleClick={() => show(p.pdk_id)} title="Double click to show what was read">
            <td>{p.pdk_id}</td><td>{p.summary.devices} ({byFamily(p.summary)})</td><td>{p.ideal_parts?.summary ? p.ideal_parts.summary.recognized : 'not read'}</td>
            <td>{loadedAt(p.loaded_utc)}</td><td className="mono">{p.sha256.slice(0, 8)}</td></tr>)}
        </tbody></table>
        <p className="hint">Double click a row to show it. To use one, choose it under "Components" in the RL model window (New model).</p></>}
      {shown && <PdkDetails pdk={shown} devices={devices} />}
    </div>);
}

const pinsText = (pins: string[]) => pins.length > 8 ? `${pins.slice(0, 8).join(' ')} ... (${pins.length} pins)` : pins.join(' ');

/** The ideal parts read with a PDK (record 7.190): what analogLib itself says about its sources, ideal R / C / L, probes and
 *  controlled sources - which Spectre component each cell netlists as, and with which pins. A PDK loaded before they were
 *  read (or by an older server) has none: the parts the project verified by hand are used until it is loaded again. */
function IdealParts({ ideal }: { ideal: Json }) {
  if (!ideal) return <p className="hint ideal-parts ideal-none">Ideal parts (sources, ideal R, C and L, probes): not read with this PDK - it was loaded
    before they were read. Press Load to read them; until then only the few parts this project verified by hand are recognized.</p>;
  const s: Json = ideal.summary, components: Json[] = ideal.components ?? [];
  return (
    <div className="ideal-parts">
      <h3 className="ideal-head">Ideal parts: {s?.recognized ?? 0} from {ideal.library}</h3>
      {ideal.error && <p className="warn">The ideal parts of {ideal.library} could not be read: {ideal.error} Until they are, only the few parts
        this project verified by hand are recognized.</p>}
      {ideal.not_read_again && <p className="warn">The last load did not read them again ({ideal.not_read_again}); shown as read on {loadedAt(ideal.read_utc)}.</p>}
      {s && <p className="hint ideal-what">What a circuit holds besides its PDK's components, read from the {s.cells} cells of {ideal.library}: {s.with_a_kind.length} have
        a kind of their own for the network ({s.with_a_kind.join(', ')}); the other {s.as_unknown} reach it as "unknown", with their pins named.
        {s.without_pins.length > 0 && ` ${ideal.library} states no pin order for ${s.without_pins.join(', ')}: a circuit holding one is refused.`}</p>}
      {components.length > 0 && <details className="ideal-list"><summary>The ideal parts ({components.length})</summary>
        <table className="grid small"><thead><tr><th>Spectre component</th><th>Kind for the network</th><th>Pins</th><th>Cells</th></tr></thead><tbody>
          {components.map(c => <tr key={c.component} title={c.basis}><td className="mono">{c.component}</td><td>{c.kind}</td>
            <td>{c.pin_orders.length ? c.pin_orders.map((o: Json) => pinsText(o.pins)).join(' | ') : '-'}</td><td>{c.cells.join(', ')}</td></tr>)}
        </tbody></table>
        <p className="hint">Cells can netlist one component with different pins ("|" separates the pin orders): a circuit is read with the order that
          has as many pins as its netlist lines have nodes. A part this project had verified before keeps the pin names its saved tasks use. Hover a row
          for how its kind was decided.</p></details>}
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
      <IdealParts ideal={pdk.ideal_parts} />
      <details><summary>Cells that are not components ({(pdk.not_netlisted?.length ?? 0) + (pdk.layout_only?.length ?? 0)})</summary>
        <ul className="hint">{(pdk.not_netlisted ?? []).map((c: Json) => <li key={c.cell}>{c.cell}: {c.reason}</li>)}
          {(pdk.layout_only ?? []).map((c: Json) => <li key={c.cell}>{c.cell}: layout only</li>)}</ul></details>
      {(pdk.not_used ?? []).length > 0 && <details><summary>In the model files but placed by no cell ({pdk.not_used.length})</summary>
        <p className="hint mono">{pdk.not_used.join(', ')}</p></details>}
      <details><summary>Model files read</summary>
        <table className="grid small"><tbody>{files.map((f: Json) => <tr key={f.path}><td className="mono">{f.path}</td><td className="numeric">{f.bytes} bytes</td><td className="mono">{String(f.sha256).slice(0, 16)}</td></tr>)}</tbody></table></details>
    </div>);
}
