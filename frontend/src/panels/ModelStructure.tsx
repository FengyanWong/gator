import { useRequest } from '../store';
import { useRef, useState } from 'react';
import { api, Json } from '../api';

// The structure of the chosen saved RL model as TABLES (no plot, no library): a short summary in the narrow run panel
// and the full layer-by-layer table in a wide dialog. Read only when the fold-out is opened (/api/runs/model/structure:
// tensor-only, checksum first). Layer types and the "never used" flag are shown only when the backend could rebuild
// the network and found exactly the saved tensors.
const n = (value: unknown) => typeof value === 'number' ? value.toLocaleString('en-US') : '?';
const share = (value: unknown) => typeof value === 'number' ? `${(100 * value).toFixed(1)} %` : '';

// `checkpointId` = the RESOLVED save point of the model described above it (null while that model is still being read).
// The fold-out stays mounted - and open - while another save point or model is chosen, and then re-reads.
export function ModelStructure({ runDir, checkpointId, label }: { runDir: string; checkpointId: string | null; label?: string }) {
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const { value: table, error, refresh } = useRequest<Json>(signal => api.modelStructure(runDir, checkpointId!, signal), [runDir, checkpointId],
    { enabled: open && !!checkpointId });

  const totals = table?.totals;
  const perNetwork = table ? table.parts[0].unused_parameters : 0;
  return (
    <details className="structure" open={open} onToggle={e => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Network structure (layers and parameter counts)</summary>
      {open && !table && !error && <p className="hint">Reading the saved tensors...</p>}
      {error && <p className="error">The structure could not be read: {error} <button onClick={refresh}>Retry read</button></p>}
      {table && <>
        <p className="hint structure-totals"><b>{n(totals.trained)} trained parameters</b> = actor {n(totals.actor)} + 2 critics x {n(totals.critic_each)} + 1 (entropy temperature).
          Also saved: 2 target copies of the critics ({n(totals.target_copies)}), which follow the critics slowly and are not trained by gradients.</p>
        {totals.never_used > 0 && <div className="note structure-unused"><p><b>{n(totals.never_used)} of the trained parameters are never used</b> ({n(perNetwork)} in each of the 3 trained networks).
          PyG's graph-transformer layer allocates <code>lin_skip</code> weights that this network switches off: the forward pass never reads them and they never get a gradient.
          Tools that simply add up tensors count them, so this network looks larger than it is.</p></div>}
        {!table.types_verified && <p className="warn structure-untyped">Layer types are not shown: {table.types_problem} Every saved tensor is still listed.</p>}
        {table.parts.map((part: Json) => (<div key={part.part} className="structure-part">
          <p className="hint"><b>{part.title}</b> - {n(part.parameters)} parameters in {part.layers.length} layers. {part.about}</p>
          <table className="grid small structure-sections"><thead><tr><th>Section</th><th>Layers</th><th>Parameters</th><th>Share</th></tr></thead><tbody>
            {part.sections.map((s: Json) => <tr key={s.section}><td>{s.section}{s.unused > 0 && <span className="hint"> ({n(s.unused)} never used)</span>}</td>
              <td className="numeric">{s.layers}</td><td className="numeric">{n(s.parameters)}</td><td className="numeric">{share(s.parameters / part.parameters)}</td></tr>)}
          </tbody></table></div>))}
        <div className="row"><button onClick={() => dialog.current?.showModal()}>Full layer table</button></div>
        <dialog ref={dialog} className="structure-dialog" onClick={e => { if (e.target === dialog.current) dialog.current?.close(); }}>
          <div className="row"><h3>Network structure{label ? ` - ${label.replace(/:[0-9a-f]{16}$/, '')}` : ''}</h3><span className="spacer" />
            <span className="hint">{table.network.encoder_type} {table.network.hidden_dim}/{table.network.heads}/{table.network.layers} - save point {table.checkpoint_id}</span>
            <button className="dialog-close" aria-label="Close" title="Close (Esc)" onClick={() => dialog.current?.close()}>{'\u00d7'}</button></div>
          <div className="structure-scroll">
            {table.parts.map((part: Json) => (<div key={part.part}>
              <h4>{part.title}: {n(part.parameters)} parameters{part.unused_parameters > 0 ? `, ${n(part.unused_parameters)} of them never used` : ''}</h4>
              <p className="hint">{part.about}</p>
              <table className="grid small structure-layers"><thead><tr><th>#</th><th>Section</th><th>Layer</th><th>Type</th><th>Shape</th><th>Parameters</th><th>Share</th><th>What it does</th></tr></thead><tbody>
                {part.layers.map((row: Json, i: number) => <tr key={row.path} className={row.unused ? 'unused' : undefined}>
                  <td className="numeric">{i + 1}</td><td className="keep">{row.section}</td><td className="path">{row.path}</td><td className="keep">{row.type ?? '-'}</td><td className="numeric">{row.shape}</td>
                  <td className="numeric">{n(row.parameters)}</td><td className="numeric">{share(row.share)}</td>
                  <td>{row.unused && <b>Never used. </b>}{row.role}{row.note && <span className="hint"> {row.note}</span>}</td></tr>)}
                <tr className="total"><td /><td /><td>Total</td><td /><td /><td className="numeric">{n(part.parameters)}</td><td className="numeric">100.0 %</td><td /></tr>
              </tbody></table></div>))}
            <p className="hint">{table.explanation} Shapes read "inputs -&gt; outputs"; a look-up table reads "entries x width". Counts are read from the tensors saved in this save point.</p>
          </div>
        </dialog></>}
    </details>);
}
