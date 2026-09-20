import { useEffect, useState } from 'react';
import { api, Json } from '../api';

const STATE_LABEL: Record<string, string> = {
  ok: 'OK', failed: 'FAILED', not_ready: 'NOT READY', not_applicable: 'n/a', not_checked: 'not checked', busy: 'BUSY', unknown: 'UNKNOWN',
};

/** Section 2.1: persistently visible indicator + per-layer detail. Observes only; never starts a tunnel. */
export function ConnectionPanel({ profileId, setProfileId }: { profileId: string | null; setProfileId: (id: string | null) => void }) {
  const [profiles, setProfiles] = useState<Json>(null);
  const [status, setStatus] = useState<Json>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.connectionProfiles().then(p => { setProfiles(p); if (!profileId && p.active) setProfileId(p.active); }).catch(e => setError(e.message)); }, []);
  useEffect(() => {
    if (!profileId) { setStatus(null); return; }
    const load = () => api.connectionStatus(profileId).then(setStatus).catch(e => setError(e.message));
    // Profile change: one automatic check of the CHEAP layers only (no Virtuoso contact), then show cached state.
    api.connectionCheck(profileId, 'cheap', 'auto').then(setStatus).catch(load);
    const id = setInterval(load, 15000);          // reads the CACHED result and its age; it never probes
    return () => clearInterval(id);
  }, [profileId]);

  const check = async (scope: string) => {
    if (!profileId) return;
    setBusy(true); setError(null);
    try { setStatus(await api.connectionCheck(profileId, scope)); setOpen(true); } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const overall = status?.overall ?? 'unknown';
  return (
    <section className="panel">
      <h3>Virtuoso / bridge connection</h3>
      {profiles && profiles.profiles.length === 0 ? (
        <p className="hint">No connection profile is configured ({profiles.connection_file}). Netlist import, manual editing, JSON
          import/export, data export and mock runs work without it.</p>
      ) : (
        <label>Profile
          <select value={profileId ?? ''} onChange={e => setProfileId(e.target.value || null)}>
            <option value="">(none)</option>
            {profiles?.profiles.map((p: Json) => <option key={p.profile_id} value={p.profile_id}>{p.profile_id}</option>)}
          </select>
        </label>
      )}
      <div className="row">
        <span className={`badge state-${overall}`} title="Overall state of the last check">{STATE_LABEL[overall] ?? overall}</span>
        <span className="hint">{status?.checked_utc ? `checked ${Math.round(status.age_seconds ?? 0)} s ago${status.stale ? ' - STALE, shown as unknown' : ''}` : 'never checked'}</span>
      </div>
      <div className="row">
        <button disabled={!profileId || busy} onClick={() => check('interactive')} title="Read-only and zero-cost: no simulation, no budget, no data rows">Test connection</button>
        <button disabled={!profileId || busy} onClick={() => check('full')} title="Adds Spectre and a license SNAPSHOT (can be slow)">+ Spectre / license</button>
        <button onClick={() => setOpen(o => !o)}>{open ? 'Hide' : 'Details'}</button>
      </div>
      {error && <p className="error">{error}</p>}
      {open && status && (
        <table className="grid small">
          <thead><tr><th>Layer</th><th>State</th><th>Reason</th></tr></thead>
          <tbody>
            {status.layers.map((l: Json) => (
              <tr key={l.layer} title={l.diagnostic ?? ''}>
                <td>{l.layer}</td><td><span className={`badge state-${l.state}`}>{STATE_LABEL[l.state] ?? l.state}</span></td>
                <td>{l.reason_code ?? ''}{l.details?.next_step && <div className="hint">Next step: {l.details.next_step}</div>}
                  {l.details?.note && <div className="hint">{l.details.note}</div>}</td>
              </tr>))}
          </tbody>
          <tfoot><tr><td colSpan={3} className="hint">Last check took {status.duration_seconds ?? '-'} s. The check observes and never
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

export function CircuitPanel({ config, setConfig, circuit, setCircuit, profileId }:
  { config: Json; setConfig: (f: (c: Json) => Json) => void; circuit: Json; setCircuit: (c: Json) => void; profileId: string | null }) {
  const [tasks, setTasks] = useState<Json[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [native, setNative] = useState<Json>(null);
  const [libraries, setLibraries] = useState<string[]>([]);
  const ref = config.circuit;
  const patch = (fields: Json) => setConfig(c => ({ ...c, circuit: { ...c.circuit, ...fields } }));

  useEffect(() => { api.tasks().then(t => setTasks(t.tasks)).catch(e => setError(e.message)); }, []);
  const load = async () => {
    setError(null);
    try { setCircuit(await api.loadCircuit(ref)); } catch (e: any) { setError(e.message); setCircuit(null); }
  };
  useEffect(() => { load(); /* reload when the reference changes */ }, [JSON.stringify(ref)]);

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
        <label title="Backend-side path inside an allowed input root. Not a browser upload folder.">Netlist path<input value={ref.netlist_path ?? ''} onChange={e => patch({ netlist_path: e.target.value })} /></label>
        <label title="Device/port mapping: port order and parameter semantics come from here, never guessed.">Device mapping (JSON)<input value={ref.parser_config_path ?? ''} onChange={e => patch({ parser_config_path: e.target.value })} /></label>
      </>)}
      {ref.source === 'virtuoso' && (<>
        <div className="row">
          <button disabled={!profileId} onClick={() => api.nativeLibraries(profileId!).then(r => setLibraries(r.libraries)).catch(e => setError(e.detail?.gate ? `Connection gate: ${e.detail.gate.blocking.join(', ')} not ok` : e.message))}>List libraries</button>
        </div>
        <label>Library<input list="libs" value={ref.library ?? ''} onChange={e => patch({ library: e.target.value })} /><datalist id="libs">{libraries.map(l => <option key={l} value={l} />)}</datalist></label>
        <label title="The installed bridge has no cell-listing call, so the cell name is typed and verified by an actual read.">Cell<input value={ref.cell ?? ''} onChange={e => patch({ cell: e.target.value })} /></label>
        <label>View<input value={ref.view ?? 'schematic'} onChange={e => patch({ view: e.target.value })} /></label>
        <label>Testbench cell<input value={ref.testbench_cell ?? ''} onChange={e => patch({ testbench_cell: e.target.value || null })} /></label>
        <button disabled={!profileId || !ref.library || !ref.cell} onClick={() => api.nativeRead(profileId!, ref.library, ref.cell).then(setNative).catch(e => setError(e.message))}>Read native schematic</button>
      </>)}
      <label title="A DUT may be identified inside one testbench; separate DUT/testbench files are not required.">DUT hierarchy / subcircuit<input value={ref.dut_hierarchy ?? ''} onChange={e => patch({ dut_hierarchy: e.target.value || null })} /></label>
      <div className="row">
        <label>Class<input value={ref.circuit_class ?? ''} onChange={e => patch({ circuit_class: e.target.value || 'unspecified' })} /></label>
        <label>PDK id<input value={ref.pdk_id ?? ''} onChange={e => patch({ pdk_id: e.target.value || 'unspecified' })} /></label>
      </div>
      {error && <p className="error">{error}</p>}
      {circuit && !circuit.loaded && <div className="blocker"><b>Blocked:</b> {circuit.blocker}
        {circuit.interface_contract && <details><summary>Interface contract</summary><pre>{JSON.stringify(circuit.interface_contract, null, 1)}</pre></details>}</div>}
      {circuit?.loaded && (<>
        {circuit.mock && <p className="mock">MOCK evaluation backend: {circuit.evaluation_backend}</p>}
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
