import { useEffect, useRef, useState } from 'react';
import { api, bytes, copy, Json, num } from '../api';
import { ModelChooser } from './ModelChooser';

function Num({ label, value, onChange, title, nullable, disabled, note }: { label: string; value: Json; onChange: (v: Json) => void; title?: string; nullable?: boolean; disabled?: boolean; note?: string }) {
  // The typed text is kept while the box has focus: "0." and "3e-" are steps towards 0.005 and 3e-4, not values.
  // It is dropped as soon as the value changes from outside (reset button, undo, another encoder), focus or not.
  const [text, setText] = useState<string | null>(null);
  const typed = text === null ? undefined : text.trim() === '' ? (nullable ? null : 0) : Number(text);
  const stale = text !== null && (typed === null || Number.isFinite(typed)) && typed !== (value ?? null);
  useEffect(() => { if (stale) setText(null); }, [stale]);
  return (
    <label title={title} className={disabled ? 'disabled' : undefined}><span>{label}{note && <span className="hint"> - {note}</span>}</span>
      <input className="numeric" value={(stale ? null : text) ?? value ?? ''} placeholder={nullable ? 'none' : ''} disabled={disabled} onBlur={() => setText(null)}
        onChange={e => { setText(e.target.value); const t = e.target.value.trim();
          if (t === '') onChange(nullable ? null : 0); else if (Number.isFinite(Number(t))) onChange(Number(t)); }} /></label>);
}

// Settings stored per encoder in the backend (src/gator_workbench/network_presets.py). The lists are
// only a fallback for the moment before the backend answers; the backend's own lists are used afterwards.
const NETWORK_FIELDS = ['hidden_dim', 'heads', 'layers'];
const ADVANCED_FIELDS = ['learning_rate', 'gamma', 'tau', 'initial_alpha', 'target_entropy_per_action', 'max_grad_norm',
  'batch_size', 'warmup_transitions', 'update_every', 'updates_per_transition', 'replay_capacity', 'episode_length'];
const pick = (source: Json, fields: string[]): Json =>
  Object.fromEntries(fields.filter(f => source?.[f] !== undefined && source?.[f] !== null).map(f => [f, source[f]]));
const Check = ({ label, value, onChange, title }: { label: string; value: boolean; onChange: (v: boolean) => void; title?: string }) => (
  <label className="check" title={title}><input type="checkbox" checked={!!value} onChange={e => onChange(e.target.checked)} />{label}</label>);

export function RunPanel({ config, setConfig, runs, circuit }: { config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; runs: Json[]; circuit: Json }) {
  const run = config.run;
  const set = (fields: Json) => setConfig(c => ({ ...c, run: { ...c.run, ...fields } }));
  const setAdv = (fields: Json) => setConfig(c => ({ ...c, run: { ...c.run, advanced: { ...(c.run.advanced ?? {}), ...fields } } }));
  const setNet = (fields: Json) => setConfig(c => ({ ...c, run: { ...c.run, network: { ...(c.run.network ?? {}), ...fields } } }));
  const source = run.model_source ?? {};
  const [model, setModel] = useState<Json>(null);
  const [error, setError] = useState<string | null>(null);
  const adv = run.advanced ?? {};
  const net = run.network ?? {};

  // Per-encoder settings live in the backend: choosing an encoder READS its settings, editing a value WRITES them back
  // for that encoder. The configuration always carries explicit values, so what is shown is what runs.
  const [netSettings, setNetSettings] = useState<Json>(null);
  const [netMessage, setNetMessage] = useState<{ level: string; text: string } | null>(null);
  const pending = useRef<{ encoder: string; body: Json } | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const netFields: string[] = netSettings?.network_fields ?? NETWORK_FIELDS;
  const advFields: string[] = netSettings?.advanced_fields ?? ADVANCED_FIELDS;
  const encoder: string = net.encoder_type ?? netSettings?.default_encoder ?? 'graph_transformer';
  const entry: Json = netSettings?.settings?.[encoder] ?? null;
  const usesHeads: boolean = entry ? !!entry.uses_heads : ['graph_transformer', 'gat'].includes(encoder);
  const remember = (e: Json) => setNetSettings((s: Json) => s && ({ ...s, settings: { ...s.settings, [e.encoder_type]: e } }));
  const applyEntry = (e: Json, record = true) => setConfig(c => ({ ...c, run: { ...c.run,
    network: { encoder_type: e.encoder_type, ...e.network }, advanced: { ...(c.run.advanced ?? {}), ...e.advanced } } }), record);
  const flush = (): Promise<void> => {
    window.clearTimeout(timer.current);
    const job = pending.current; pending.current = null;
    if (!job) return Promise.resolve();
    return api.saveNetworkSettings(job.encoder, job.body)
      .then(e => { remember(e); setNetMessage({ level: 'ok', text: `Saved in the backend as the ${e.encoder_type} setting.` }); })
      .catch(e => setNetMessage({ level: 'error', text: `Not saved in the backend: ${e.message}` }));
  };
  const queueSave = (network: Json, advanced: Json) => {
    // The complete value set is sent, so hidden and heads are judged together (one at a time could never pass).
    pending.current = { encoder, body: { network: pick(network, netFields), advanced: pick(advanced, advFields) } };
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, 700);
  };
  const editNet = (fields: Json) => { setNet(fields); queueSave({ ...net, ...fields }, adv); };
  const editAdv = (fields: Json) => { setAdv(fields); queueSave(net, { ...adv, ...fields }); };
  const chooseEncoder = (name: string) => {
    setNetMessage(null);
    const cached = netSettings?.settings?.[name];
    if (cached) applyEntry(cached); else setNet({ encoder_type: name });
    // An unsaved edit still belongs to the previous encoder; then read the backend again (another tab may have changed it).
    flush().then(() => api.networkSettings()).then(s => {
      setNetSettings(s);
      const fresh = s.settings?.[name];
      if (fresh && JSON.stringify([fresh.network, fresh.advanced]) !== JSON.stringify([cached?.network, cached?.advanced])) applyEntry(fresh, false);
    }).catch(() => undefined);
  };
  const reset = (to: string) => {
    pending.current = null; window.clearTimeout(timer.current);
    api.resetNetworkSettings(encoder, to).then(e => {
      remember(e); applyEntry(e);
      setNetMessage({ level: 'ok', text: to === 'publication' ? `${encoder}: publication preset restored in the backend.` : `${encoder}: GATOR baseline stored in the backend.` });
    }).catch(e => setNetMessage({ level: 'error', text: e.message }));
  };
  useEffect(() => {
    api.networkSettings().then(setNetSettings).catch(e => setNetMessage({ level: 'error', text: `Backend network settings unavailable (${e.message}).` }));
    return () => { flush(); };
  }, []);
  // A configuration that leaves a value out would silently run the schema default. Fill it from the backend instead.
  useEffect(() => {
    if (!entry) return;
    const missingNet = netFields.filter(f => net[f] === undefined || net[f] === null);
    const missingAdv = advFields.filter(f => adv[f] === undefined || adv[f] === null);
    if (net.encoder_type && !missingNet.length && !missingAdv.length) return;
    setConfig(c => ({ ...c, run: { ...c.run,
      network: { ...(c.run.network ?? {}), ...pick(entry.network, missingNet), encoder_type: encoder },
      advanced: { ...(c.run.advanced ?? {}), ...pick(entry.advanced, missingAdv) } } }), false);
  }, [entry, JSON.stringify(net), JSON.stringify(adv)]);
  const differs = !!entry && !pending.current && (netFields.some(f => net[f] !== undefined && net[f] !== entry.network[f])
    || advFields.some(f => adv[f] !== undefined && adv[f] !== entry.advanced[f]));
  const originLabel = entry && ({ publication: 'publication preset', gator_baseline: 'GATOR baseline', custom: 'edited, saved in the backend' } as Json)[entry.origin];
  const budget: number = run.max_evaluations;
  const starved = run.mode !== 'frozen' && typeof budget === 'number' && (budget <= (adv.warmup_transitions ?? 0) || budget < (adv.batch_size ?? 0) + 1);
  // A checkpoint only loads into the network it was trained with.
  const savedModel: Json = run.mode !== 'scratch' ? model?.description?.contract?.model_config : null;
  const savedSac: Json = model?.description?.contract?.sac_config;
  const archDiffers = !!savedModel && (savedModel.encoder_type !== encoder || netFields.some(f => savedModel[f] !== net[f]));
  const matchCheckpoint = () => setConfig(c => ({ ...c, run: { ...c.run,
    network: { encoder_type: savedModel.encoder_type, ...pick(savedModel, netFields) }, advanced: { ...(c.run.advanced ?? {}), ...pick(savedSac, advFields) } } }));

  // Default the RL model to the last model used by this project, and its `latest` checkpoint (not `best`).
  useEffect(() => {
    if (source.run_dir) return;
    api.defaultModel(config.project.name).then(d => d.run_dir && set({ model_source: { ...source, run_dir: d.run_dir, checkpoint_id: 'latest' } })).catch(() => undefined);
  }, [config.project.name]);
  useEffect(() => {
    setModel(null); setError(null);
    if (!source.run_dir) return;
    api.model(source.run_dir, source.checkpoint_id ?? 'latest', config).then(setModel).catch(e => setError(e.message));
  }, [source.run_dir, source.checkpoint_id, run.mode, JSON.stringify(net), JSON.stringify(adv), JSON.stringify(config.targets), JSON.stringify(config.parameters)]);

  return (
    <section className="panel">
      <h3>Run configuration</h3>
      <label title="scratch: random init, new run. resume: same task, same run, full state. fine_tune: compatible weights, new task, new run with a parent. frozen: no updates at all.">Mode
        <select value={run.mode} onChange={e => set({ mode: e.target.value })}>
          {['scratch', 'resume', 'fine_tune', 'frozen'].map(m => <option key={m} value={m}>{m}</option>)}</select></label>
      {model?.suggestion && model.suggestion.mode !== run.mode && <p className="warn">Suggested: <b>{model.suggestion.mode}</b> - {model.suggestion.reason}
        {model.suggestion.requires_confirmation ? ' (needs your confirmation)' : ''} <button onClick={() => set({ mode: model.suggestion.mode })}>Use</button></p>}
      <Num label="Concurrent Spectre jobs" value={run.concurrency} onChange={v => set({ concurrency: v })} title="Independent simulation jobs at once. NOT the thread count of one simulation." />
      {circuit?.max_concurrency && run.concurrency > circuit.max_concurrency && <p className="error">This task supports at most {circuit.max_concurrency} jobs.</p>}
      <Num label="Threads per job" value={run.threads_per_job} onChange={v => set({ threads_per_job: v })} title="Simulator threads inside each job. Recorded; applied only by backends that support it." />
      <Num label="Evaluation budget (max_evaluations)" value={run.max_evaluations} onChange={v => set({ max_evaluations: v })}
        title="NEW candidate evaluations that may START in the whole run, shared by all workers. Baselines, warm-up and failures count. Episode resets do not reset it." />
      <Num label="Max Spectre launches" nullable value={run.max_spectre_launches} onChange={v => set({ max_spectre_launches: v })} title="Optional hard cap incl. retries and failures." />
      <Num label="Max retries per evaluation" value={run.max_retries ?? 0} onChange={v => set({ max_retries: v })} title="A retry keeps the evaluation_id and costs a launch, not an evaluation." />
      <Num label="Wall-time limit (s)" nullable value={run.max_wall_seconds} onChange={v => set({ max_wall_seconds: v })} />
      <Num label="Random seed (target task)" value={run.seed} onChange={v => set({ seed: v })} title="Seed of THIS run. The source model's pretraining seed is recorded separately." />
      <Check label="Stop at the first feasible design" value={run.stop_at_first_feasible} onChange={v => set({ stop_at_first_feasible: v })} />
      <h3>RL network</h3>
      <p className="hint">Independent of the agent language model. "No weights" means scratch, but an architecture is still required.
        Every encoder keeps its own settings in the backend: choosing one loads them, editing a value (here or under Advanced) saves it for that encoder.</p>
      <label>Encoder<select value={encoder} onChange={e => chooseEncoder(e.target.value)}>
        {(netSettings?.encoders ?? ['graph_transformer', 'mlp', 'rgcn', 'gat', 'port_gnn', 'gcn']).map((m: string) => <option key={m}>{m}</option>)}</select></label>
      <div className="row"><Num label="hidden" value={net.hidden_dim ?? entry?.network?.hidden_dim ?? 32} onChange={v => editNet({ hidden_dim: v })} />
        <Num label="heads" value={net.heads ?? entry?.network?.heads ?? 4} onChange={v => editNet({ heads: v })} disabled={!usesHeads} note={usesHeads ? undefined : 'ignored by this encoder'}
          title={usesHeads ? 'Attention heads. hidden must be divisible by heads.' : 'Only graph_transformer and gat have attention heads. The number is still written into the checkpoint, so it is kept fixed here.'} />
        <Num label="layers" value={net.layers ?? entry?.network?.layers ?? 2} onChange={v => editNet({ layers: v })} /></div>
      {entry && <><p className="hint in-use">In use: <b>{originLabel}</b></p>
        <div className="row pair">
          <button disabled={entry.origin === 'publication' && !differs} onClick={() => reset('publication')} title="Forget the saved values of this encoder and return to the values taken from publications.">Publication preset</button>
          <button disabled={entry.origin === 'gator_baseline' && !differs} onClick={() => reset('gator_baseline')} title="The equal-size setting of all existing GATOR evidence and checkpoints. Suited to short runs.">GATOR baseline</button></div></>}
      {differs && <p className="warn">These values differ from the backend's saved {encoder} setting.
        <button onClick={() => applyEntry(entry)}>Load backend values</button> <button onClick={() => { queueSave(net, adv); flush(); }}>Save these to the backend</button></p>}
      {entry?.problem && <p className="warn">{entry.problem}</p>}
      {netMessage && <p className={netMessage.level === 'error' ? 'error' : 'hint'}>{netMessage.text}</p>}
      {starved && <p className="warn">Budget {budget} with warm-up {adv.warmup_transitions} and batch size {adv.batch_size}: {budget <= (adv.warmup_transitions ?? 0) ? 'every evaluation is a random warm-up action, so the policy never acts' : 'one batch is never filled, so the network never learns'}.
        Published settings assume thousands of simulations. Lower them under Advanced, raise the budget, or use the GATOR baseline.</p>}
      {entry && <details><summary>Where the {encoder} values come from</summary>
        <p className="hint">{entry.summary}</p>
        <table className="grid small"><thead><tr><th>Setting</th><th>Preset</th><th>Basis</th><th>Source and note</th></tr></thead><tbody>
          {[...netFields, ...advFields].map(f => { const p = entry.provenance?.[f]; const ref = p?.source ? netSettings.references?.[p.source] : null; return (
            <tr key={f}><td>{f}</td><td className="numeric">{num(p?.value)}</td><td>{p?.basis}{p?.match === 'closest' ? ', closest network' : ''}</td>
              <td>{ref && <a href={ref.url} target="_blank" rel="noreferrer">{ref.short}</a>} {p?.note}</td></tr>); })}
        </tbody></table>
        <p className="hint">{netSettings.scale_note}</p></details>}
      <ModelChooser mode={run.mode} source={source} runs={runs} outputRoot={config.output?.output_root} network={{ encoder_type: encoder, ...pick(net, netFields) }}
        onChoose={(run_dir, checkpoint_id) => set({ model_source: { ...source, run_dir, checkpoint_id } })} />
      {run.mode !== 'scratch' && (<>
        {error && <p className="error">{error}</p>}
        {archDiffers && <p className="warn">This checkpoint was trained with {savedModel.encoder_type}, hidden {savedModel.hidden_dim}, heads {savedModel.heads}, layers {savedModel.layers}.
          Its weights cannot be loaded into a different network. <button onClick={matchCheckpoint}>Use the checkpoint's network</button></p>}
        {model?.description && <table className="grid small model-facts"><tbody>
          <tr><td>Trained on</td><td>{model.description.source_task_id}</td></tr>
          <tr><td>Saved (UTC)</td><td>{model.description.created_utc}</td></tr>
          <tr><td>Schema</td><td>{model.description.metadata_version}</td></tr>
          <tr><td>Training</td><td>{model.description.counters.evaluations_committed} evaluations, {model.description.counters.learner_updates} updates, replay {model.description.counters.replay_size}</td></tr>
          <tr><td>Restorable</td><td><b>{model.description.restoration_capability}</b>{model.description.missing_components.length ? ` - missing: ${model.description.missing_components.join(', ')}` : ''}</td></tr>
          <tr><td>Folder</td><td className="path" title="Click to copy" onClick={() => copy(model.description.path)}>{model.description.path}</td></tr>
        </tbody></table>}
        {model?.compatibility && <details open={!model.compatibility.compatible}><summary className={model.compatibility.compatible ? '' : 'error'}>Compatibility for {model.compatibility.mode}: {model.compatibility.compatible ? 'compatible' : 'NOT compatible - there is no fallback to scratch'}</summary>
          <ul>{model.compatibility.checks.map((c: Json) => <li key={c.component} className={`issue ${c.status === 'ok' ? 'info' : c.status === 'warning' ? 'warning' : 'error'}`}>{c.component}: {c.status} - {c.detail}</li>)}</ul></details>}
        {run.mode === 'frozen' && <label>Frozen actions<select value={run.frozen_action ?? 'deterministic'} onChange={e => set({ frozen_action: e.target.value })}><option>deterministic</option><option>sampled</option></select></label>}
        {run.mode === 'fine_tune' && <Check label="Continual learning (inherit weights fine-tuned on a previous test task)" value={run.continual_learning} onChange={v => set({ continual_learning: v })} />}
      </>)}
      <details><summary>Advanced (stored per encoder, like the network sizes)</summary>
        <p className="hint">These belong to the selected encoder's backend setting. The algorithm stays soft actor-critic; only its numbers change.</p>
        <Num label="Learning rate" value={adv.learning_rate ?? entry?.advanced?.learning_rate ?? 3e-4} onChange={v => editAdv({ learning_rate: v })} />
        <Num label="Batch size" value={adv.batch_size ?? entry?.advanced?.batch_size ?? 8} onChange={v => editAdv({ batch_size: v })} title="A learner update needs this many stored transitions." />
        <Num label="Warm-up transitions" value={adv.warmup_transitions ?? entry?.advanced?.warmup_transitions ?? 8} onChange={v => editAdv({ warmup_transitions: v })} title="Random actions until this many transitions are stored. They count against the budget." />
        <Num label="Update every N transitions" value={adv.update_every ?? entry?.advanced?.update_every ?? 1} onChange={v => editAdv({ update_every: v })} />
        <Num label="Updates per transition (UTD)" value={adv.updates_per_transition ?? entry?.advanced?.updates_per_transition ?? 1} onChange={v => editAdv({ updates_per_transition: v })} />
        <Num label="Episode length" value={adv.episode_length ?? entry?.advanced?.episode_length ?? 4} onChange={v => editAdv({ episode_length: v })} />
        <Num label="Replay capacity" value={adv.replay_capacity ?? entry?.advanced?.replay_capacity ?? 10000} onChange={v => editAdv({ replay_capacity: v })} />
        <div className="row"><Num label="Discount gamma" value={adv.gamma ?? entry?.advanced?.gamma ?? 0.99} onChange={v => editAdv({ gamma: v })} />
          <Num label="Target mixing tau" value={adv.tau ?? entry?.advanced?.tau ?? 0.005} onChange={v => editAdv({ tau: v })} /></div>
        <div className="row"><Num label="Initial alpha" value={adv.initial_alpha ?? entry?.advanced?.initial_alpha ?? 0.2} onChange={v => editAdv({ initial_alpha: v })} title="Starting entropy temperature of soft actor-critic. It is learned afterwards." />
          <Num label="Target entropy / action" value={adv.target_entropy_per_action ?? entry?.advanced?.target_entropy_per_action ?? 1} onChange={v => editAdv({ target_entropy_per_action: v })} />
          <Num label="Max grad norm" value={adv.max_grad_norm ?? entry?.advanced?.max_grad_norm ?? 10} onChange={v => editAdv({ max_grad_norm: v })} /></div>
        <Check label="Freeze encoder (fine_tune)" value={adv.freeze_encoder} onChange={v => setAdv({ freeze_encoder: v })} />
        <Check label="Encoder-only transfer (fine_tune)" value={adv.encoder_only_transfer} onChange={v => setAdv({ encoder_only_transfer: v })} />
        <Check label="Reset critic (fine_tune)" value={adv.reset_critic} onChange={v => setAdv({ reset_critic: v })} />
        <Num label="Pause after N consecutive infrastructure failures" value={run.max_consecutive_infrastructure_failures ?? 3} onChange={v => set({ max_consecutive_infrastructure_failures: v })} />
      </details>
    </section>
  );
}

export function OutputPanel({ config, setConfig, meta, activeRun }: { config: Json; setConfig: (f: (c: Json) => Json) => void; meta: Json; activeRun: Json }) {
  const out = config.output;
  const set = (fields: Json) => setConfig(c => ({ ...c, output: { ...c.output, ...fields } }));
  const root = out.output_root ?? meta?.output_root ?? '';
  const [check, setCheck] = useState<Json>(null);
  const [browse, setBrowse] = useState<Json>(null);
  const locked = !!activeRun?.worker_alive;
  useEffect(() => { if (root) api.checkOutput(root).then(setCheck).catch(() => setCheck(null)); }, [root]);
  const paths = activeRun?.paths;
  return (
    <section className="panel">
      <h3>Output settings</h3>
      <label title="A backend directory inside an allowed root. Not a browser upload folder.">Output root
        <input value={root} disabled={locked} onChange={e => set({ output_root: e.target.value })} /></label>
      <div className="row"><button disabled={locked} onClick={() => api.browse().then(setBrowse)}>Browse allowed roots...</button>
        <button onClick={() => root && api.checkOutput(root, true).then(setCheck)}>Test writability</button><button onClick={() => copy(root)}>Copy path</button></div>
      {locked && <p className="hint">The run directory is locked while a run is active. A resumed run writes back to its original directory.</p>}
      {browse && <ul className="tree">{browse.parent && <li onClick={() => api.browse(browse.parent).then(setBrowse)}>..</li>}
        {browse.entries.map((e: Json) => <li key={e.path}><span onClick={() => api.browse(e.path).then(setBrowse)}>{e.name}</span> <button onClick={() => { set({ output_root: e.path }); setBrowse(null); }}>select</button></li>)}</ul>}
      {check && <table className="grid small"><tbody>
        <tr><td>Resolved</td><td className="path">{check.resolved ?? '-'}</td></tr>
        <tr><td>Allowed / writable</td><td className={check.allowed && check.writable ? '' : 'error'}>{String(check.allowed)} / {String(check.writable)} {check.error ?? ''}</td></tr>
        <tr><td>Backend host</td><td>{check.host} ({check.environment}, {check.filesystem})</td></tr>
        <tr><td>Free space</td><td>{bytes(check.free_bytes)}; used here {bytes(check.bytes_used)}</td></tr>
        <tr><td>Windows path</td><td>{check.windows_path ?? <span className="hint">not shown: {check.windows_mapping}</span>}{check.windows_path && <span className="hint"> (verified by read-back)</span>}</td></tr>
        <tr><td>Mock data root</td><td className="path">{check.mock_data_root}</td></tr>
      </tbody></table>}
      <div className="row"><label>Experiment name<input value={out.experiment_name ?? ''} onChange={e => set({ experiment_name: e.target.value })} /></label>
        <label title="Set to append runs to an existing experiment; empty creates a new unique ID.">Experiment ID<input value={out.experiment_id ?? ''} placeholder="new" onChange={e => set({ experiment_id: e.target.value || null })} /></label></div>
      {paths && <details open><summary>Current run paths</summary><table className="grid small"><tbody>
        {Object.entries(paths).map(([k, v]) => <tr key={k}><td>{k}</td><td className="path" onClick={() => copy(String(v))}>{String(v)}</td></tr>)}
        <tr><td>bytes written</td><td>{bytes(activeRun?.bytes_written ?? activeRun?.persistence?.bytes_written)}</td></tr>
        <tr><td>last successful save</td><td>{activeRun?.persistence?.last_successful_save ?? '-'}</td></tr>
        <tr><td>remote Spectre work dir</td><td className="hint">local work/ for this task; final files are written directly here (sync: local)</td></tr>
      </tbody></table></details>}
      <h4>Always saved</h4><p className="hint">Configuration/provenance snapshots, per-evaluation records, actual parameters, metrics, simulator-job accounting, run summary, event/error logs (Parquet + JSON).</p>
      <Check label="Learner-update log" value={out.save_learner_updates ?? true} onChange={v => set({ save_learner_updates: v })} />
      <Check label="Model checkpoints" value={out.save_checkpoints ?? true} onChange={v => set({ save_checkpoints: v })} />
      <Check label="Replay snapshots (needed for a FULL resume)" value={out.save_replay_snapshots ?? true} onChange={v => set({ save_replay_snapshots: v })} />
      {out.save_replay_snapshots === false && <p className="warn">Without replay snapshots checkpoints are weights_only: a full training-state resume of this run will NOT be possible.</p>}
      <Check label="Complete transition archive (independent of replay snapshots)" value={out.save_transition_archive ?? true} onChange={v => set({ save_transition_archive: v })} />
      <Check label="Experiment summary CSVs" value={out.export_summary_csv ?? true} onChange={v => set({ export_summary_csv: v })} />
      <div className="row"><Num label="Checkpoint every N evaluations" nullable value={out.checkpoint_every_evaluations ?? 50} onChange={v => set({ checkpoint_every_evaluations: v })} />
        <Num label="or every S seconds" nullable value={out.checkpoint_every_seconds} onChange={v => set({ checkpoint_every_seconds: v })} /></div>
      <label title="Raw PSF only; nothing is rendered. Applies to raw outputs that actually exist.">Raw waveform retention
        <select value={out.waveform_retention ?? 'best_and_failures'} onChange={e => set({ waveform_retention: e.target.value })}><option>none</option><option>best_and_failures</option><option>all</option></select></label>
      <Num label="Waveform storage limit (bytes)" nullable value={out.waveform_storage_limit_bytes ?? 2147483648} onChange={v => set({ waveform_storage_limit_bytes: v })}
        title="Oldest retained failures are removed first. The best design, models and primary data are never deleted automatically." />
      <p className="hint">Pausing, stopping and normal completion always save safely. Detailed CSV copies are exported on demand; raw tables are Parquet.</p>
    </section>
  );
}

export function ResearchPanel({ config, setConfig }: { config: Json; setConfig: (f: (c: Json) => Json) => void }) {
  const r = config.research ?? {};
  const set = (fields: Json) => setConfig(c => ({ ...c, research: { ...(c.research ?? {}), ...fields } }));
  const list = (v: string) => v.split(',').map(s => s.trim()).filter(Boolean);
  return (
    <details className="panel"><summary><b>Research experiments</b> (optional for a single run; missing labels stay "unspecified")</summary>
      <label>Experiment group<input value={r.experiment_group ?? 'unspecified'} onChange={e => set({ experiment_group: e.target.value })} /></label>
      <label>Split<select value={r.split ?? 'unspecified'} onChange={e => set({ split: e.target.value })}>{['unspecified', 'train', 'validation', 'test'].map(s => <option key={s}>{s}</option>)}</select></label>
      <label>Generalization level<select value={r.generalization_level ?? 'unspecified'} onChange={e => set({ generalization_level: e.target.value })}>
        {['unspecified', 'same_task', 'unseen_spec', 'unseen_topology', 'unseen_circuit_class'].map(s => <option key={s}>{s}</option>)}</select></label>
      <label>Training sources<input value={(r.training_sources ?? []).join(', ')} onChange={e => set({ training_sources: list(e.target.value) })} /></label>
      <label>Test tasks<input value={(r.test_tasks ?? []).join(', ')} onChange={e => set({ test_tasks: list(e.target.value) })} /></label>
      <label title="Associates runs with the same target, initial dimensions, budget, test setup and target seed.">Comparison pair ID<input value={r.comparison_pair_id ?? 'unspecified'} onChange={e => set({ comparison_pair_id: e.target.value })} /></label>
      <div className="row"><Num label="Task order K" nullable value={r.task_order} onChange={v => set({ task_order: v })} /><Num label="Pretrain seed (source)" nullable value={r.pretrain_seed} onChange={v => set({ pretrain_seed: v })} /></div>
      <label>Budget checkpoints<input value={(r.budget_checkpoints ?? []).join(', ')} onChange={e => set({ budget_checkpoints: list(e.target.value).map(Number).filter(Number.isFinite) })} /></label>
      <label>Method label<input value={r.method_label ?? 'unspecified'} onChange={e => set({ method_label: e.target.value })} placeholder="Scratch | Pretrained-Frozen | Pretrained-Fine-tuned | encoder-only transfer" /></label>
      <label>Ablation labels<input value={(r.ablation_labels ?? []).join(', ')} onChange={e => set({ ablation_labels: list(e.target.value) })} /></label>
    </details>
  );
}
