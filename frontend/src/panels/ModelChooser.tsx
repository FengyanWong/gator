import { useEffect, useRef, useState } from 'react';
import { api, copy, Json } from '../api';

// Which saved RL model a resume / fine_tune / frozen run loads. Plain words on purpose: a "run" is one training
// session (one press of Start), the models it saved live in its own folder, and every save is a "save point".
// The list comes from /api/runs/models (small metadata files only); the chosen model is verified by /api/runs/model.
const KIND: Record<string, string> = { periodic: 'automatic save', manual: 'saved with "Save now"', pause: 'saved at pause', stop: 'saved at stop',
  final: 'saved at the end of the run', safety: 'safety save' };
const when = (utc?: string | null) => { const d = utc ? new Date(utc) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'unknown time'; };
const netLabel = (n: Json) => n?.encoder_type ? `${n.encoder_type} ${n.hidden_dim}/${n.heads}/${n.layers}` : 'unknown network';
const pointLabel = (p: Json) => `${p.evaluations ?? '?'} evaluations - ${when(p.created_utc)} - ${KIND[p.kind] ?? p.kind}${p.restoration_capability !== 'full_state' ? ' - weights only' : ''}`;
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

export function ModelChooser({ mode, source, onChoose, runs, outputRoot, network }: {
  mode: string; source: Json; onChoose: (run_dir: string | null, checkpoint_id: string) => void;
  runs: Json[]; outputRoot?: string | null; network: Json }) {
  const [models, setModels] = useState<Json[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('');
  const request = useRef(0);
  const load = () => {
    const mine = ++request.current;
    setLoading(true);
    api.savedModels(outputRoot ?? undefined)
      .then(r => { if (mine === request.current) { setModels(r.models ?? []); setError(null); } })
      .catch(e => { if (mine === request.current) { setModels([]); setError(e.message); } })
      .finally(() => { if (mine === request.current) setLoading(false); });
  };
  const wanted = mode !== 'scratch';
  // Read when the block opens, and again whenever the application refreshed its run list (a run started or ended).
  // No timer: the "Refresh list" button is the only other trigger.
  useEffect(() => { if (wanted) load(); }, [wanted, runs, outputRoot]);

  if (!wanted) return (<>
    <h3>RL model to load</h3>
    <p className="hint model-none">None. Mode is <b>scratch</b>, so training starts from random weights and no saved model is loaded.
      To reuse a saved model, change Mode at the top of this panel: <b>fine_tune</b> keeps training it in a new run,
      <b> frozen</b> uses it as it is without any learning, <b>resume</b> continues the run that saved it.</p></>);

  const current: Json = models?.find(m => m.run_dir === source.run_dir) ?? null;
  const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
  const text = (m: Json) => [m.task_name, m.task_id, m.circuit_task, m.circuit_class, netLabel(m.network), m.mode, m.state, m.mock ? 'mock' : 'real', `seed${m.seed}`].join(' ').toLowerCase();
  const shown = (models ?? []).filter(m => m.run_dir === source.run_dir || words.every(w => text(m).includes(w)));
  const otherNetwork = (m: Json) => !!m.network?.encoder_type && ['encoder_type', 'hidden_dim', 'heads', 'layers'].some(f => network?.[f] !== undefined && m.network[f] !== network[f]);
  const chosen: string = source.checkpoint_id ?? 'latest';
  const newest: Json = current?.checkpoints.find((p: Json) => p.is_latest) ?? current?.checkpoints[current.checkpoints.length - 1];
  const best: Json = current?.checkpoints.find((p: Json) => p.is_best_policy);
  const known = chosen === 'latest' || (chosen === 'best_policy' ? !!best : !!current?.checkpoints.some((p: Json) => p.checkpoint_id === chosen));

  return (<>
    <h3>RL model to load</h3>
    <p className="hint">A saved model is the trained RL network that a run wrote to disk. A <b>run</b> is one training session (one press of Start);
      it keeps its models in its own folder. Pick a run's model, then one of its save points.</p>
    <div className="row"><button onClick={load} disabled={loading}>Refresh list</button>
      <span className="hint model-count">{loading ? 'Reading the saved models...' : models ? `${plural(models.length, 'saved model')} under the output folder` : ''}</span></div>
    {error && <p className="error">The list of saved models could not be read: {error}</p>}
    {models && !models.length && !error && <p className="hint model-empty">No saved model yet under this output folder. A run saves one when it is paused, stopped or finished,
      and every N evaluations while it runs ("Model checkpoints" in the output settings must be on).</p>}
    {models && models.length > 5 && <input className="model-filter" placeholder="Filter: task, circuit, network, mock / real ..." value={filter} onChange={e => setFilter(e.target.value)} />}
    {source.run_dir && models && !current && !loading && <p className="warn model-missing">The selected model is not in this list: its run folder is outside the current output folder, or it no longer holds a complete save point.
      <span className="path" onClick={() => copy(source.run_dir)}> {source.run_dir}</span> <button onClick={() => onChoose(null, 'latest')}>Clear the selection</button></p>}
    {!!shown.length && <div className="model-list" role="radiogroup" aria-label="Saved models">
      {shown.map(m => { const active = m.run_dir === source.run_dir; return (
        <button key={m.run_dir} role="radio" aria-checked={active} className={`model-card${active ? ' active' : ''}`} title={m.run_dir}
          onClick={() => { if (!active) onChoose(m.run_dir, 'latest'); }}>
          <span className="model-title"><b>{m.task_name ?? m.task_id}</b>{m.mock && <span className="badge model-tag mock-tag">MOCK</span>}
            {otherNetwork(m) && <span className="badge model-tag" title="Trained with another network than the one set above. Its weights only load into its own network: after choosing it, use the button 'Use the checkpoint's network'.">other network</span>}
            {m.restoration_capability !== 'full_state' && <span className="badge model-tag" title="Saved without the replay snapshot: usable for fine_tune and frozen, but its run cannot be resumed.">weights only</span>}</span>
          <span>{m.circuit_task ?? m.circuit_class ?? 'unknown circuit'} - {netLabel(m.network)}</span>
          <span>{m.trained_evaluations ?? '?'} evaluations of training - {plural(m.checkpoints.length, 'save point')}</span>
          <span className="hint">last saved {when(m.saved_utc)} - run {m.state ?? 'unknown'} ({m.mode}, seed {m.seed})</span>
        </button>); })}</div>}
    {models && !!models.length && !shown.length && <p className="hint">No saved model matches the filter.</p>}
    {current && <>
      <label title="Latest save = the most recently SAFELY saved state of that run (default). It is not automatically the best policy.">Save point
        <select className="model-point" value={chosen} onChange={e => onChoose(current.run_dir, e.target.value)}>
          <option value="latest">Latest save (default): {newest ? pointLabel(newest) : 'none'}</option>
          {best && <option value="best_policy">Best policy (picked by a validation rule): {pointLabel(best)}</option>}
          {[...current.checkpoints].reverse().map((p: Json) => <option key={p.checkpoint_id} value={p.checkpoint_id}>{pointLabel(p)}</option>)}
          {!known && <option value={chosen}>{chosen === 'best_policy' ? 'Best policy: this run has none' : `${chosen}: no longer in this run`}</option>}
        </select></label>
      {!known && <p className="warn">{chosen === 'best_policy' ? (current.best_policy?.reason ?? 'No best policy was selected in this run.') : 'That save point is not in the run folder any more.'} Choose another save point.</p>}
      <p className="hint">"Latest save" follows the run: if that run trains further, its newest save is loaded. A dated save point always stays the same model.
        Save points are never deleted automatically.</p></>}
  </>);
}
