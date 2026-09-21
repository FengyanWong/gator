import { useEffect, useRef, useState } from 'react';
import { api, copy, Json } from '../api';

const STATE_LABEL: Record<string, string> = {
  ok: 'OK', failed: 'FAILED', not_ready: 'NOT READY', not_applicable: 'n/a', not_checked: 'not checked', busy: 'BUSY', unknown: 'UNKNOWN',
};

/** A fixed clock time instead of a running "N s ago": nothing re-renders this panel on a timer, so an age would freeze. */
const testedAt = (iso: string) => {
  const at = new Date(iso);
  return at.toDateString() === new Date().toDateString() ? at.toLocaleTimeString() : at.toLocaleString();
};

/** Section 2.1 plus the explicit connect flow: 1 Connect SSH -> 2 load the command in the CIW -> 3 Test connection.
 *  A TEST only observes and never starts anything. The tunnel is started by the "Connect SSH" click alone - never on
 *  page load or on a timer - and nothing here ever stops or restarts a tunnel, the daemon or Virtuoso.
 *  The panel itself checks nothing on its own either: it reads the backend's last result once and probes only on a
 *  button press, so a shown result is the one of the last press (with its clock time) until the next press. */
export function ConnectionPanel({ profileId, setProfileId }: { profileId: string | null; setProfileId: (id: string | null) => void }) {
  const [profiles, setProfiles] = useState<Json>(null);
  const [setup, setSetup] = useState<Json>(null);
  const [status, setStatus] = useState<Json>(null);
  const [connected, setConnected] = useState<Json>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const loadProfiles = () => api.connectionProfiles().then(p => {
    setProfiles(p); if (!profileId && p.active) setProfileId(p.active);
    if (p.profiles.length === 0) api.connectionSetup().then(setSetup).catch(e => setError(e.message));   // locates files; reads none
  }).catch(e => setError(e.message));
  useEffect(() => { loadProfiles(); }, []);
  useEffect(() => {
    setConnected(null);
    if (!profileId) { setStatus(null); return; }
    // Profile change / page load: show the last result the backend remembers. This READS the cache and probes nothing.
    // A check runs only on a button press below (user request 2026-09-20): no automatic check, no timer.
    let live = true;
    api.connectionStatus(profileId).then(s => { if (live) setStatus(s); }).catch(e => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [profileId]);

  const run = async (name: string, action: () => Promise<void>) => {
    setBusy(name); setError(null);
    try { await action(); } catch (e: any) { setError(e.message); } finally { setBusy(null); }
  };
  const createProfile = () => run('profile', async () => { const made = await api.connectionCreateProfile('lab'); setProfiles(made.profiles); setProfileId(made.profile_id); });
  const connect = () => run('connect', async () => { const answer = await api.connectionConnect(profileId!); setConnected(answer.connect); setStatus(answer.status); });
  const check = (scope: string) => run(scope, async () => { setStatus(await api.connectionCheck(profileId!, scope)); });
  const copyText = (key: string, text: string) => { copy(text); setCopied(key); setTimeout(() => setCopied(c => (c === key ? null : c)), 1500); };

  const overall = status?.overall ?? 'unknown';
  const summary = status?.summary;
  const ciw = connected?.details?.ciw ?? status?.ciw ?? null;
  const tunnelUp = status?.layers?.some((l: Json) => l.layer === 'tunnel' && (l.state === 'ok' || l.state === 'not_applicable'));
  return (
    <section className="panel">
      <h3>Virtuoso bridge connection</h3>
      {profiles && profiles.profiles.length === 0 ? (
        <div>
          <p className="hint">No connection profile is configured yet ({profiles.connection_file}). Netlist import, manual editing,
            JSON import/export, data export and mock runs work without it.</p>
          {setup && <ul className="steps-list">
            <li className={setup.env_file_exists ? 'ok' : 'error'}>{setup.env_file_exists ? 'found' : 'missing'}: bridge env file {setup.env_file}</li>
            <li className={setup.bridge_importable || setup.bridge_site_packages ? 'ok' : 'error'}>
              {setup.bridge_importable ? 'virtuoso-bridge is importable by the backend' : setup.bridge_site_packages ? `found: bridge package in ${setup.bridge_site_packages}` : 'missing: virtuoso-bridge package'}</li>
            {setup.problems.map((p: Json) => <li key={p.reason_code} className="hint">{p.message}</li>)}
          </ul>}
          <button disabled={!setup?.can_create || !!busy} onClick={createProfile}
            title="Writes the connection file from the bridge setup found on this machine. The target host stays in the bridge env file; the browser sends only the profile name.">
            {busy === 'profile' ? 'Creating...' : 'Create profile "lab" from this bridge setup'}</button>
        </div>
      ) : (
        <label>Profile
          <select value={profileId ?? ''} onChange={e => setProfileId(e.target.value || null)}>
            <option value="">(none)</option>
            {profiles?.profiles.map((p: Json) => <option key={p.profile_id} value={p.profile_id}>{p.profile_id}</option>)}
          </select>
        </label>
      )}
      <div className="row">
        <span className={`badge state-${overall}`} title="Overall state of the last test">{STATE_LABEL[overall] ?? overall}</span>
        <span className="hint">{status?.checked_utc ? `tested at ${testedAt(status.checked_utc)}${status.stale ? ' - too old to trust, shown as unknown' : ''}` : 'never tested'}</span>
      </div>

      <div className="step">
        <div className="step-head"><span className="step-no">1</span> Connect to the target over SSH</div>
        <div className="row">
          <button disabled={!profileId || !!busy} onClick={connect}
            title="Starts the SSH tunnel of this profile, exactly like `virtuoso-bridge start`. A tunnel that is already running is left untouched. Nothing is ever stopped or restarted.">
            {busy === 'connect' ? 'Connecting... (can take a minute)' : tunnelUp ? 'Connect SSH (already up)' : 'Connect SSH'}</button>
        </div>
        {connected && <p className={connected.ok ? 'ok' : 'error'}>
          {connected.ok ? (connected.action === 'already_running' ? 'SSH tunnel was already running - left untouched.' : `SSH tunnel started (${connected.duration_seconds} s).`)
            : `Connect failed: ${connected.reason_code}${connected.diagnostic ? ` - ${connected.diagnostic}` : ''}`}
          {connected.details?.next_step && <span className="hint"> Next step: {connected.details.next_step}</span>}</p>}
      </div>

      <div className="step">
        <div className="step-head"><span className="step-no">2</span> Load the bridge in the Virtuoso CIW</div>
        {ciw ? (
          <div>
            <p className="hint">Paste this line into the CIW input line of your running Virtuoso, press Enter, then test below.</p>
            <div className="command"><code>{ciw.load}</code><button onClick={() => copyText('load', ciw.load)}>{copied === 'load' ? 'Copied' : 'Copy'}</button></div>
            <details><summary className="hint">CIW says "already running", or other trouble</summary>
              <p className="hint">Replace a running daemon (two lines):</p>
              <div className="command"><code>{ciw.replace_running_daemon.join('\n')}</code>
                <button onClick={() => copyText('replace', ciw.replace_running_daemon.join('\n'))}>{copied === 'replace' ? 'Copied' : 'Copy'}</button></div>
              <ul className="steps-list">{ciw.notes.map((n: string) => <li key={n} className="hint">{n}</li>)}</ul>
            </details>
          </div>
        ) : <p className="hint">The command appears here once the SSH tunnel is up (step 1): the bridge reports the setup file it placed on the Virtuoso host.</p>}
      </div>

      <div className="step">
        <div className="step-head"><span className="step-no">3</span> Test the connection</div>
        <div className="row">
          <button disabled={!profileId || !!busy} onClick={() => check('interactive')} title="Read-only and zero-cost: one trivial SKILL round trip. No simulation, no budget, no data rows. It never starts anything.">
            {busy === 'interactive' ? 'Testing...' : 'Test connection'}</button>
          <button disabled={!profileId || !!busy} onClick={() => check('full')} title="Adds Spectre and a license SNAPSHOT (can be slow)">{busy === 'full' ? 'Testing...' : '+ Spectre / license'}</button>
          <button onClick={() => setOpen(o => !o)}>{open ? 'Hide' : 'Details'}</button>
        </div>
        {summary && <div className={`status-line level-${summary.level}`}>
          <strong>{summary.headline}</strong>
          {summary.next_step && <div className="hint">Next step: {summary.next_step}</div>}
        </div>}
      </div>
      {error && <p className="error">{error}</p>}
      {open && status && (
        <table className="grid small">
          <thead><tr><th>Layer</th><th>State</th><th>Reason</th></tr></thead>
          <tbody>
            {status.layers.map((l: Json) => (
              <tr key={l.layer} title={l.diagnostic ?? ''}>
                <td>{l.layer}</td><td><span className={`badge state-${l.state}`}>{STATE_LABEL[l.state] ?? l.state}</span></td>
                <td>{l.reason_code ?? ''}{l.diagnostic && <div className="hint">{l.diagnostic}</div>}
                  {l.details?.next_step && <div className="hint">Next step: {l.details.next_step}</div>}
                  {l.details?.note && <div className="hint">{l.details.note}</div>}</td>
              </tr>))}
          </tbody>
          <tfoot><tr><td colSpan={3} className="hint">Last test took {status.duration_seconds ?? '-'} s. A test observes and never
            starts, restarts or stops the tunnel, the daemon or Virtuoso. It is not the costed baseline simulation.
            {status.run_active && ` A run is active; last successful bridge interaction: ${status.last_successful_bridge_interaction_utc ?? 'none yet'}.`}</td></tr></tfoot>
        </table>
      )}
    </section>
  );
}

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
/** "1.2G", "800M", "1.2e9" -> Hz. NaN when it is not a number. */
const parseFrequency = (text: string) => {
  const match = /^\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*([kMG]?)(?:Hz)?\s*$/.exec(text);
  return match ? Number(match[1]) * ({ '': 1, k: 1e3, M: 1e6, G: 1e9 } as Record<string, number>)[match[2]] : NaN;
};
const EXAMPLE_NETLIST = { netlist_path: 'tests/fixtures/synthetic/opamp.scs', parser_config_path: 'configs/opamp.json' };

/** What the Agent tab is asked once a cell was read from Virtuoso. Shown in the message box first: editable, never sent by itself. */
const DRAFT_PROMPT = 'Read this circuit and say in two or three sentences what it is and how it works. Then propose: which device sizes to vary, '
  + 'which of them must move together (matched or identical devices), a sensible range for each, and targets with the measurements they need.';

export function CircuitPanel({ config, setConfig, circuit, setCircuit, profileId, meta, onAgent }:
  { config: Json; setConfig: (f: (c: Json) => Json) => void; circuit: Json; setCircuit: (c: Json) => void; profileId: string | null; meta: Json;
    onAgent: (kind: string, selection: Json[], prompt?: string) => void }) {
  const [tasks, setTasks] = useState<Json[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [native, setNative] = useState<Json>(null);
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
  const patch = (fields: Json) => { edited.current = true; setConfig(c => ({ ...c, circuit: { ...c.circuit, ...fields } })); };
  const netlistReady = !!ref.netlist_path?.trim() && !!ref.parser_config_path?.trim();
  const root = meta?.repo_root ? `${meta.repo_root}/` : '';     // absolute, so the example does not depend on where the backend was started
  const example = { netlist_path: root + EXAMPLE_NETLIST.netlist_path, parser_config_path: root + EXAMPLE_NETLIST.parser_config_path };

  useEffect(() => { api.tasks().then(t => setTasks(t.tasks)).catch(e => setError(e.message)); }, []);
  const load = async (reference: Json) => {
    const mine = ++request.current;
    setError(null); setLoading(true);
    try { const loaded = await api.loadCircuit(reference); if (mine === request.current) setCircuit(loaded); }
    catch (e: any) { if (mine === request.current) { setError(labelled(e.message)); setCircuit(null); } }
    finally { if (mine === request.current) setLoading(false); }
  };
  useEffect(() => {
    const key = JSON.stringify(ref), typed = edited.current;
    edited.current = false;
    if (pressed.current === key) { pressed.current = null; return; }
    // A netlist is loaded by its button (or Enter), never while its paths are being typed or still missing: asking the
    // backend then only produced "Blocked: needs netlist_path ..." the moment the source was chosen. Whatever was
    // loaded before no longer belongs to this reference, so it is cleared. A complete reference that arrives from
    // outside this panel (imported configuration, approved proposal) still loads by itself, like a registered task.
    if (ref.source === 'netlist' && (typed || !netlistReady)) { request.current++; setLoading(false); setError(null); setCircuit(null); return; }
    load(ref);
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
    const layers = gate ? [...(gate.blocking ?? []), ...(gate.uncertain ?? [])].join(', ') : '';
    setNativeError({ step, outdated, text: outdated ? 'This backend is older than the page and cannot do this yet: restart it (gator_workbench.cli serve).'
      : gate ? `Virtuoso cannot be reached (${layers || gate.status}). Bring the link up in the connection panel above, then try again.` : e.message });
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
      if (answer.technology_library) setConfig(c => ((c.circuit.pdk_id ?? 'unspecified') === 'unspecified'
        ? { ...c, circuit: { ...c.circuit, pdk_id: answer.technology_library } } : c));
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
  // Create profile: the cell that was read + the rows of the three editors become the task real:<name>. Nothing is
  // contacted; whatever the real backend cannot do comes back as a plain reason. The rows return snapped onto the width grid.
  const [profileName, setProfileName] = useState('');
  const [recipe, setRecipe] = useState('ring_oscillator');
  const [frequency, setFrequency] = useState('');
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<Json>(null);
  const suggestedName = (ref.cell ?? '').toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/^[^a-z]+/, '').slice(0, 40);
  const createProfile = async () => {
    setCreating(true); setNativeError(null);
    try {
      const made = await api.createProfile(config, profileName || suggestedName, recipe, recipe === 'ring_oscillator' ? parseFrequency(frequency) : null);
      setCreated(made);
      api.tasks().then(t => setTasks(t.tasks)).catch(() => undefined);
      setConfig(c => ({ ...c, parameters: made.parameters, circuit: { ...c.circuit, source: 'registered_task', task_id: made.task_key, circuit_class: made.circuit_class, pdk_id: made.pdk_id } }));
    } catch (e: any) { setNativeError({ step: 'profile', text: e.message }); }
    finally { setCreating(false); }
  };
  // A generated profile, before its first costed run: check it against the live cell WITHOUT simulating (the run adapter
  // connects, Virtuoso exports, the export is compared, the deck is written), and afterwards record the finished baseline
  // as the profile's reference. Both are explicit presses; neither starts a simulation.
  const [preflight, setPreflight] = useState<Json>(null);
  const [profileBusy, setProfileBusy] = useState<string | null>(null);
  const [profileMessage, setProfileMessage] = useState<Json>(null);
  const generatedName = ref.source === 'registered_task' && circuit?.generated_profile ? String(ref.task_id ?? '').replace(/^real:/, '') : null;
  useEffect(() => { setPreflight(null); setProfileMessage(null); }, [generatedName]);
  const profileAction = async (what: string, action: () => Promise<void>) => {
    setProfileBusy(what); setProfileMessage(null);
    try { await action(); }
    catch (e: any) {
      const gate = e.detail?.gate, layers = gate ? [...(gate.blocking ?? []), ...(gate.uncertain ?? [])].join(', ') : '';
      setProfileMessage({ level: 'error', text: e.status === 404 || e.status === 405 ? 'This backend is older than the page and cannot do this yet: restart it (gator_workbench.cli serve).'
        : gate ? `Virtuoso cannot be reached (${layers || gate.status}). Bring the link up in the connection panel above, then try again.` : e.message });
    } finally { setProfileBusy(null); }
  };
  const checkProfile = () => profileAction('check', async () => { setPreflight(await api.profilePreflight(generatedName!, profileId!)); });
  const recordReference = () => profileAction('reference', async () => {
    const recorded = await api.profileReference(generatedName!);
    setProfileMessage({ level: 'ok', text: `Baseline recorded from run ${recorded.run_id ?? recorded.run_dir}. Every later run compares its first evaluation with it.` });
    await load(ref);
  });
  const [importing, setImporting] = useState(false);
  const importCell = async () => {
    setImporting(true); setNativeError(null);
    try { await api.nativeImport(profileId!, ref.library, ref.cell, ref.testbench_cell ?? null); await load(ref); }
    catch (e: any) { nativeProblem('import', e); }
    finally { setImporting(false); }
  };

  const useStarter = async () => {
    try { const starter = await api.starter(ref.task_id); setConfig(c => ({ ...c, ...starter, run: { ...c.run, ...starter.run }, output: c.output, research: c.research })); }
    catch (e: any) { setError(e.message); }
  };
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
          <select value={ref.task_id ?? ''} onChange={e => patch({ task_id: e.target.value })}>
            {tasks.map(t => <option key={t.task_key} value={t.task_key}>{t.task_key}{t.kind === 'mock' ? '  [MOCK]' : t.available ? '' : '  [blocked]'}</option>)}
          </select>
        </label>
        {ref.task_id?.startsWith('synthetic:') && <button onClick={useStarter} title="Fills the three editors from the fixture's declared groups. Everything stays editable.">Load starter configuration</button>}
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
        {!netlistReady ? (
          <div className="hint">
            <p>Two files are needed. Both are read on the computer that runs the workbench - nothing is uploaded from the browser:</p>
            <ul className="steps-list">
              <li><b>Netlist path</b> - the Spectre netlist (.scs).</li>
              <li><b>Device mapping (JSON)</b> - says, for each device type in the netlist, which pin is which and what its parameters mean.
                The workbench never guesses this. The project's own mappings are in <code>configs/</code> (<code>configs/opamp.json</code>, <code>configs/gpdk045_opamp.json</code>, ...).</li>
            </ul>
            <p>Both must be inside {(meta?.allowed_input_roots ?? []).map((r: string) => <code key={r}>{r} </code>)}
              (another folder: start the backend with <code>--allow-input-root DIR</code>). A Windows path such as <code>D:\gator\my.scs</code> is
              converted for you. Fill in both, then press <b>Load netlist</b>.</p>
          </div>
        ) : !circuit && !error && !loading && <p className="hint">Not loaded yet - press <b>Load netlist</b> (or Enter).</p>}
      </>)}
      {ref.source === 'virtuoso' && (<>
        {!profileId && <p className="hint">Choose a connection profile in the panel above: the libraries are read from that Virtuoso.</p>}
        <label>Library
          <select value={ref.library ?? ''} disabled={!libraries} onChange={e => patch({ library: e.target.value || null, cell: null, view: null, testbench_cell: null })}>
            <option value="">{listing === 'libraries' ? 'Reading the libraries...' : libraries ? `(choose one of ${libraries.length})` : '(not listed)'}</option>
            {withCurrent(libraries ?? [], ref.library).map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
        {nativeError?.outdated && nativeError.step === 'cells' ? (<>
          <label title="Typed, because this backend cannot list cells yet.">Cell<input value={ref.cell ?? ''} onChange={e => patch({ cell: e.target.value || null, view: 'schematic' })} /></label>
          <button disabled={!profileId || !ref.library || !ref.cell} onClick={() => { nativeStep('schematic', () => api.nativeRead(profileId!, ref.library, ref.cell), setNative); }}>Read native schematic</button>
        </>) : (<>
          <label title="Only a cell with a schematic view can be read.">Cell
            <select value={ref.cell ?? ''} disabled={!cells} onChange={e => patch({ cell: e.target.value || null, view: e.target.value ? 'schematic' : null })}>
              <option value="">{!ref.library ? '(choose a library first)' : listing === 'cells' ? 'Reading the cells...' : cells ? `(choose one of ${cells.cells.length})` : '(not listed)'}</option>
              {withCurrent((cells?.cells ?? []).map((c: Json) => c.name), ref.cell).map(name => {
                const readable = !cells || cells.cells.find((c: Json) => c.name === name)?.has_schematic !== false;
                return <option key={name} value={name} disabled={!readable}>{name}{readable ? '' : '  (no schematic view)'}</option>;
              })}
            </select>
          </label>
          {chosenCell && <p className="hint">View: <b>schematic</b> - the only view the reader opens, so there is nothing to choose.
            {chosenCell.views.length > 1 && ` This cell also has: ${chosenCell.views.filter((v: string) => v !== 'schematic').join(', ')}.`}</p>}
          <label title="Optional. The cell that holds the test setup around the design, if it is a separate cell.">Testbench cell
            <select value={ref.testbench_cell ?? ''} disabled={!cells} onChange={e => patch({ testbench_cell: e.target.value || null })}>
              <option value="">(none)</option>
              {withCurrent((cells?.cells ?? []).filter((c: Json) => c.has_schematic).map((c: Json) => c.name), ref.testbench_cell).map(name => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
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
      <p className="hint">Circuit class and PDK id are labels saved with every run. They do not change the simulation or the optimization;
        "unspecified" is fine for a single run.{ref.source === 'virtuoso' && ' The PDK id is filled in from the library\'s technology library.'}</p>
      {error && <p className="error">{error}</p>}
      {circuit && !circuit.loaded && ref.source === 'virtuoso' && (
        // Not a fault and nothing to fix in this form: said in plain words, with the way to the circuits that do work.
        <div className="note">
          <p><b>Browse only: you can look at this cell here, but the workbench cannot optimize it yet.</b></p>
          <p>To optimize a circuit in the real Virtuoso, the workbench needs a <i>circuit profile</i> - a checked description of three things:</p>
          <ul className="steps-list">
            <li>which device sizes it may change, within which limits and in which steps (Virtuoso rounds what is typed, so this is tested for each circuit);</li>
            <li>which testbench simulates the circuit, and under which conditions;</li>
            <li>how the results - gain, frequency, current ... - are read from the simulation.</li>
          </ul>
          <p>{tasks.filter(t => t.kind === 'real').length} circuits have one today. Click one to work with it:</p>
          <div className="row">{tasks.filter(t => t.kind === 'real').map(t =>
            <button key={t.task_key} title={t.available ? t.description : t.blocker} onClick={() => patch({ source: 'registered_task', task_id: t.task_key })}>{t.task_key}</button>)}</div>
          <p><b>To start a profile for this cell</b>, read it into the workbench: Virtuoso exports its netlist
            {ref.testbench_cell ? <> (through the testbench <code>{ref.testbench_cell}</code>)</> : <> (choose its <b>Testbench cell</b> above first, if it has one)</>} and
            the device sizes are read. Read-only, no simulation, some seconds. The agent can then tell you what the circuit is and suggest what to vary.</p>
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
        {circuit.native_draft && (
          <div className="note">
            <p><b>Read from Virtuoso. Not optimizable yet: it has no circuit profile.</b> The workbench now holds its own copy of this cell,
              so you can look at it, fill the three editors and let the agent help. Start stays disabled.</p>
            <p>Next: ask the agent what this circuit is and which sizes, ranges and targets make sense. Its answer is a proposal in the
              Agent tab; once you approve it there, the three editors are filled from it.</p>
            <div className="row">
              <button className="primary" onClick={() => onAgent('draft_config', [], DRAFT_PROMPT)} title="Opens the Agent tab with the request written out. Nothing is sent until you press Send there.">Ask the agent for suggestions</button>
              <button disabled={!profileId || importing || !!listing} onClick={importCell} title="After a change in Virtuoso, or to export through another testbench cell. Read-only.">{importing ? 'Reading...' : 'Read the cell again'}</button>
            </div>
            {circuit.profile_task ? (
              <p><b>This cell already has the profile <code>{circuit.profile_task}</code>.</b>{' '}
                <button onClick={() => patch({ source: 'registered_task', task_id: circuit.profile_task })}>Open {circuit.profile_task}</button></p>
            ) : (<>
              <p><b>Then create the profile.</b> It takes what may vary from the parameter editor (only transistor widths can be changed
                in the real Virtuoso; ranges are snapped onto its 5 nm width grid) and registers the cell as a task. No simulation runs:
                the first real one is the new task's <b>Single baseline simulation</b>, which asks for your budget.</p>
              <div className="row">
                <label title="Lowercase letters, digits and _. It becomes the task real:<name>.">Profile name
                  <input value={profileName} placeholder={suggestedName} onChange={e => setProfileName(e.target.value)} /></label>
                <label title="Decides which analysis runs and how results become numbers.">Circuit type
                  <select value={recipe} onChange={e => setRecipe(e.target.value)}>
                    {(circuit.profile_recipes ?? []).map((r: Json) => <option key={r.id} value={r.id}>{r.label}</option>)}</select></label>
              </div>
              {recipe === 'ring_oscillator' && <label title="Rough is enough: it only sizes the transient simulation (60 periods long, measured after 20).">Expected oscillation frequency
                <input value={frequency} placeholder="e.g. 1.2G" onChange={e => setFrequency(e.target.value)} /></label>}
              <div className="row"><button className="primary" onClick={createProfile}
                disabled={creating || !(profileName || suggestedName) || (recipe === 'ring_oscillator' && !(parseFrequency(frequency) > 0))}>
                {creating ? 'Creating...' : 'Create profile'}</button></div>
            </>)}
          </div>)}
        {created && circuit.generated_profile && <div className="note"><p><b>Profile {created.task_key} created.</b> The parameter editor now shows the
          ranges exactly as registered. Nothing has been simulated yet.</p></div>}
        {circuit.generated_profile && !circuit.baseline_recorded && <p className="warn">Generated profile without a real baseline: begin with
          <b> Single baseline simulation</b> (one real Spectre run, asks for your budget) before an optimization run.</p>}
        {generatedName && (
          <div className="note">
            <p><b>Before the first costed run:</b> check this profile against the cell in Virtuoso. It does everything a real evaluation does
              before Spectre starts - connect, export the netlist, compare it with the record, write the simulation deck - and simulates nothing.</p>
            <div className="row">
              <button disabled={!profileId || !!profileBusy} onClick={checkProfile} title="Read-only and zero-cost. Needs the link up and no ADE/Maestro window open on the design.">
                {profileBusy === 'check' ? 'Checking...' : 'Check against Virtuoso (no simulation)'}</button>
              {!circuit.baseline_recorded && <button disabled={!!profileBusy} onClick={recordReference}
                title="After a finished Single baseline simulation of this task: its result becomes the reference that every later run is compared with. Recorded once, never replaced.">
                {profileBusy === 'reference' ? 'Recording...' : 'Record the baseline run as reference'}</button>}
            </div>
            {preflight && <ul className="steps-list">
              {preflight.steps.map((s: Json) => <li key={s.step} className={s.ok ? 'ok' : 'error'}><b>{s.ok ? 'passed' : 'FAILED'}: {s.step}</b> - {s.detail}</li>)}
              <li className={preflight.ok ? 'ok' : 'error'}><b>{preflight.ok ? 'The profile matches the live cell. Nothing was simulated.' : 'Not ready for a real run: see the failed step.'}</b></li>
            </ul>}
            {profileMessage && <p className={profileMessage.level === 'ok' ? 'ok' : 'error'}>{profileMessage.text}</p>}
          </div>)}
        {circuit.notes?.map((n: string) => <p key={n} className="hint">{n}</p>)}
        <h3>Hierarchy ({circuit.summary.device_count} instances)</h3>
        <Tree node={circuit.hierarchy} />
        {circuit.summary.unknown_devices.length > 0 && <p className="warn">Unmapped devices need confirmation: {circuit.summary.unknown_devices.join(', ')}</p>}
        {circuit.diagnostics.length > 0 && <details><summary>{circuit.diagnostics.length} diagnostics</summary><ul>{circuit.diagnostics.map((d: Json, i: number) => <li key={i} className={d.severity}>{d.code}: {d.message}</li>)}</ul></details>}
        <details><summary>Instances and parameters</summary>
          <table className="grid small"><thead><tr><th>Instance</th><th>Kind</th><th>Parameters (canonical units)</th></tr></thead>
            <tbody>{circuit.summary.devices.map((d: Json) => <tr key={d.instance_path}><td>{d.instance_path}</td><td>{d.kind}</td>
              <td>{Object.entries(d.parameters).map(([k, v]: [string, any]) => `${k}=${v.value ?? v.expression ?? '?'}`).join('  ')}</td></tr>)}</tbody></table>
        </details>
      </>)}
      {native && <details open><summary>Native schematic {native.library}/{native.cell} ({native.instance_count} instances, as read)</summary>
        <p className="warn">Requires confirmation: {native.requires_confirmation.join('; ')}</p>
        <table className="grid small"><tbody>{native.instances.map((i: Json) => <tr key={i.instance_path}><td>{i.instance_path}</td><td>{i.master.library}/{i.master.cell}</td>
          <td>{Object.entries(i.parameters).map(([k, v]: [string, any]) => `${k}=${v.raw}`).join('  ')}</td></tr>)}</tbody></table></details>}
    </section>
  );
}
