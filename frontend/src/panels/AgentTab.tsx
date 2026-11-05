import { useEffect, useRef, useState } from 'react';
import { call, type Json } from '../api';
import { Icon } from './Icons';

type Model = { id: string; name: string; provider: string; source: string; description: string; size: number;
  installed: boolean; deployed: boolean; storage: string | null; error: string | null; runtime: string; vram_gib: number; ram_gib: number };
type Status = { models: Model[]; active_job: string | null; deployed: string | null; default_model: string | null; mode: string };
type Check = { compatible: boolean; errors: string[]; note: string; local_asset_available: boolean; runtime_ready: boolean; disk_needed: number;
  host: { disk_free: number | null; ram_total: number | null; ram_free: number | null; gpus: { name: string; free: number; total: number }[] } };
type Change = { path: string; label: string; before: Json; after: Json; unit: string | null };
type Review = { config: Json; changes: Change[]; warnings: { message: string }[] };
type Result = { message: string; proposal: Json; proposal_error: string | null; preview?: Review; omitted_messages: number };
type Job = { id: string; kind: string; model_id: string; state: string; phase: string; bytes: number; total: number | null;
  error: string | null; output: string; offset: number; result: Result | null };
type Message = { role: 'user' | 'assistant'; content: string; job?: string; result?: Result };
const root = '/api/local-agent';
const gib = (n: number | null) => n === null ? 'unknown' : `${(n / 1024 ** 3).toFixed(1)} GiB`;
const errorText = (e: unknown) => e instanceof Error ? e.message : String(e);

/** Kept mounted with the bottom panel: switching tabs does not discard an answer or its cancellation control. */
export function AgentTab({ hidden, config, setConfig }: { hidden: boolean; config: Json; setConfig: (next: Json | ((c: Json) => Json)) => void }) {
  const [opened, setOpened] = useState(false), [status, setStatus] = useState<Status | null>(null);
  const [checks, setChecks] = useState<Record<string, Check>>({}), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [jobId, setJobId] = useState<string | null>(null), [job, setJob] = useState<Job | null>(null);
  const [stream, setStream] = useState(''), [messages, setMessages] = useState<Message[]>([]), [draft, setDraft] = useState('');
  const [liveOpen, setLiveOpen] = useState(false);
  const [applied, setApplied] = useState<Record<string, boolean>>({});
  const [pendingApply, setPendingApply] = useState<{ id: string; next: Json } | null>(null);
  const generation = useRef<Record<string, { revision: number; config: Json }>>({});
  const current = useRef({ config, revision: 0 });
  if (current.current.config !== config) current.current = { config, revision: current.current.revision + 1 };
  const finished = useRef(new Set<string>()), offset = useRef(0);
  const active = !!jobId;

  useEffect(() => {
    if (!pendingApply) return;
    if (config === pendingApply.next) {
      setApplied(v => ({ ...v, [pendingApply.id]: true }));
      setNotice('Changes applied as one Undo step. Save the task when ready.');
    } else {
      setError('The editor changed before application. No proposed changes were applied.');
    }
    setPendingApply(null);
  }, [config, pendingApply]);

  useEffect(() => { if (!hidden) setOpened(true); }, [hidden]);
  const refresh = async () => {
    const next = await call<Status>('GET', root);
    setStatus(next);
    if (next.active_job) setJobId(next.active_job);
    return next;
  };
  useEffect(() => {
    if (!opened || hidden && !active) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await call<Status>('GET', root);
        if (!stopped) { setStatus(next); if (next.active_job) setJobId(next.active_job); }
      } catch (e) { if (!stopped) setError(errorText(e)); }
      if (!stopped) timer = setTimeout(poll, 4000);
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [opened, hidden, active]);

  useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    offset.current = 0; setStream('');
    const poll = async () => {
      try {
        const next = await call<Job>('GET', `${root}/jobs/${jobId}?offset=${offset.current}`);
        if (stopped) return;
        offset.current = next.offset;
        setJob(next); setStream(s => s + next.output);
        if (next.state !== 'running') {
          setStream(''); setLiveOpen(false); // The completed answer lives in messages; release the temporary stream.
          if (!finished.current.has(jobId)) {
            finished.current.add(jobId);
            if (next.kind === 'chat' && next.state === 'completed' && next.result) {
              const result = next.result;
              setMessages(m => [...m, { role: 'assistant', content: result.message, job: jobId, result }]);
            }
            if (next.error) setError(next.error);
            if (next.state === 'cancelled') setNotice('Operation cancelled. No suggestion was applied.');
            if (next.kind === 'install' && next.state === 'completed') setNotice('Model installed. Deploy verifies its actual load before enabling chat.');
          }
          setJobId(null); await refresh(); return;
        }
      } catch (e) { if (!stopped) setError(errorText(e)); }
      if (!stopped) timer = setTimeout(poll, 600);
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [jobId]);

  const check = async (id: string) => {
    const result = await call<Check>('GET', `${root}/models/${id}/compatibility`);
    setChecks(c => ({ ...c, [id]: result }));
    return result;
  };
  const operate = async (model: Model, action: 'install' | 'deploy' | 'undeploy' | 'delete' | 'check') => {
    setBusy(true); setError(''); setNotice('');
    try {
      if (action === 'check') { await check(model.id); return; }
      if (action === 'install' || action === 'deploy') {
        const result = await check(model.id);
        if (!result.compatible) { setError(result.errors.join(' ')); return; }
      }
      const result = await call<{ job_id?: string; external_file_preserved?: boolean }>('POST', `${root}/models/${model.id}`, { action });
      if (result.job_id) { setJob(null); setJobId(result.job_id); }
      if (action === 'delete') setNotice(result.external_file_preserved ? 'Model registration deleted. The external benchmark file was preserved.' : 'Managed model deleted.');
      if (action === 'undeploy') setNotice('Model undeployed. Any active inference is being cancelled.');
      await refresh();
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  const send = async () => {
    const text = draft.trim(), model = status?.deployed;
    if (!text || !model || busy || active) return;
    setBusy(true); setError(''); setNotice('');
    const snapshot = { ...current.current };
    const next: Message[] = [...messages, { role: 'user', content: text }];
    try {
      const response = await call<{ job_id: string }>('POST', `${root}/chat`, { model_id: model, config: snapshot.config,
        messages: next.map(m => ({ role: m.role, content: m.content })) });
      generation.current[response.job_id] = snapshot;
      setMessages(next); setDraft(''); setJob(null); setJobId(response.job_id);
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  const apply = async (id: string) => {
    setBusy(true); setError('');
    try {
      const snapshot = generation.current[id];
      if (!snapshot || current.current.revision !== snapshot.revision) throw new Error('Suggestion is stale. Ask again with the current configuration.');
      const reviewed = await call<Review>('POST', `${root}/jobs/${id}/review`, { config: snapshot.config });
      if (current.current.revision !== snapshot.revision) throw new Error('The editor changed during validation. No changes applied.');
      // Recheck at reducer execution too: an already queued editor change must never be overwritten.
      setConfig((now: Json) => now === snapshot.config ? reviewed.config : now);
      setPendingApply({ id, next: reviewed.config });
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!jobId) return;
    try { await call('POST', `${root}/jobs/${jobId}/cancel`); }
    catch (e) { setError(errorText(e)); }
  };
  const newConversation = () => {
    setMessages([]); setStream(''); setJob(null); setApplied({});
    generation.current = {}; finished.current.clear();
    setNotice('New conversation. Current editor configuration will be included.');
  };

  return <section className="agent-panel" hidden={hidden} aria-label="Local Agent">
    <div className="agent-heading"><strong>Agent</strong><span>A language model on this computer that advises on parameters and run settings</span></div>
    <p className="agent-note">Install a model once, deploy it, then ask. Every suggestion is shown as a table of changes first; nothing
      changes until you press Apply changes, and Undo takes it back. The Agent never starts a simulation.</p>
    {error && <p className="agent-error" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!status && <p>Reading the list of models…</p>}
    <div className="agent-columns">
      <div className="agent-catalog" aria-label="NVIDIA model catalog">
        <h4 className="agent-column-title">Models</h4>
        {status?.models.map(model => <article className="agent-model" key={model.id}>
          <div className="agent-model-heading"><strong>{model.name}</strong>
            <span className={`agent-state${model.deployed ? ' ready' : ''}`}>{model.deployed ? 'Ready · loads per reply' : model.installed ? 'Installed' : 'Not installed'}</span></div>
          <p>{model.description}</p>
          <table className="agent-needs"><tbody>
            <tr><th scope="row">Download</th><td>{gib(model.size)}</td></tr>
            <tr><th scope="row">Needs</th><td>{model.vram_gib} GiB free GPU memory and {model.ram_gib} GiB RAM</td></tr>
            <tr><th scope="row">Runs with</th><td>{model.runtime}</td></tr>
            <tr><th scope="row">Source</th><td><a href={model.source} target="_blank" rel="noreferrer">NVIDIA model card</a></td></tr>
          </tbody></table>
          <div className="agent-controls">
            <button title={`Check compatibility for ${model.name}`} disabled={busy || active} onClick={() => void operate(model, 'check')}><Icon name="refresh" label={`Check compatibility for ${model.name}`} /></button>
            <button title={`Install ${model.name}`} disabled={busy || active || model.installed} onClick={() => void operate(model, 'install')}><Icon name="download" label={`Install ${model.name}`} /></button>
            <button title={`Deploy ${model.name}`} disabled={busy || active || !model.installed || !!status.deployed} onClick={() => void operate(model, 'deploy')}><Icon name="play" label={`Deploy ${model.name}`} /></button>
            <button title={`Undeploy ${model.name}`} disabled={busy || !(model.deployed || active && job?.kind === 'deploy' && job.model_id === model.id)} onClick={() => void operate(model, 'undeploy')}><Icon name="stop" label={`Undeploy ${model.name}`} /></button>
            <button title={model.storage === 'external' ? `Delete registration for ${model.name}; keep external file` : `Delete ${model.name}`} disabled={busy || active || !model.installed || model.deployed} onClick={() => void operate(model, 'delete')}><Icon name="delete" label={`Delete ${model.name}`} /></button>
          </div>
          {model.storage === 'external' && <p className="agent-note">The model file lives outside the workbench: Delete forgets it here and keeps the file.</p>}
          {checks[model.id] && <div className="agent-check" role="status">
            <strong>{checks[model.id].compatible ? 'This computer can run it' : 'This computer cannot run it now'}</strong>
            <ul>
              <li>{checks[model.id].host.gpus.length ? checks[model.id].host.gpus.map(g => `${g.name}: ${gib(g.free)} of GPU memory free`).join('; ') : 'No GPU found'}</li>
              <li>RAM: {gib(checks[model.id].host.ram_free)} free of {gib(checks[model.id].host.ram_total)}</li>
              <li>Disk: {gib(checks[model.id].host.disk_free)} free</li>
              {checks[model.id].errors.map((e, i) => <li key={i} className="agent-error">{e}</li>)}
            </ul>
            <p>{checks[model.id].local_asset_available ? 'A model file is already on this computer; its checksum is verified before it is used.' : 'The model file is downloaded from NVIDIA and its checksum verified.'} {checks[model.id].note}</p>
          </div>}
          {model.error && <p className="agent-error">{model.error}</p>}
        </article>)}
      </div>
      <div className="agent-conversation">
        <h4 className="agent-column-title">Conversation</h4>
        {active && <div className="agent-operation" role="status"><strong>{job?.phase || 'Starting…'}</strong>
          {job?.total ? <><progress max={job.total} value={job.bytes} aria-label="Installation progress" /><span>{gib(job.bytes)} of {gib(job.total)}</span></> : <span>Working on this computer…</span>}
          <button onClick={() => void cancel()} title="Cancel Agent operation"><Icon name="stop" label="Cancel Agent operation" /></button>
        </div>}
        {active && stream && <details className="agent-live" onToggle={e => setLiveOpen(e.currentTarget.open)}>
          <summary>Live model output</summary>{liveOpen && <pre>{stream}</pre>}</details>}
        <div className="agent-messages" aria-label="Agent conversation">
          {messages.map((m, i) => <article key={i} className={`agent-message ${m.role}`}>
            <strong>{m.role === 'user' ? 'You' : 'Agent'}</strong><p>{m.content}</p>
            {m.result?.omitted_messages ? <p className="agent-note">The model saw the current configuration and the newest messages; {m.result.omitted_messages} older messages no longer fit its memory.</p> : null}
            {m.result?.proposal_error && <p className="agent-error" role="alert">Suggestion rejected: {m.result.proposal_error}</p>}
            {m.result?.preview && m.job && <div className="agent-proposal">
              <strong>Proposed editor changes</strong><table><thead><tr><th>Setting</th><th>Current</th><th>Proposed</th></tr></thead><tbody>
                {m.result.preview.changes.map(c => <tr key={c.path}><th>{c.label}</th><td>{String(c.before ?? 'unset')} {c.unit}</td><td>{String(c.after)} {c.unit}</td></tr>)}
              </tbody></table>
              {m.result.preview.warnings.map((w, n) => <p key={n} className="agent-note">{w.message}</p>)}
              <button disabled={busy || active || applied[m.job] || generation.current[m.job]?.revision !== current.current.revision}
                onClick={() => void apply(m.job!)}>Apply changes</button>
              {applied[m.job] ? <span className="agent-proposal-state">Applied through the editor</span> : generation.current[m.job]?.revision !== current.current.revision ? <span className="agent-proposal-state">Stale suggestion: the editor changed since, ask again</span> : <span className="agent-proposal-state">Checked again when applied; Undo takes it back</span>}
            </div>}
          </article>)}
        </div>
        {status?.deployed ? <form className="agent-compose" onSubmit={e => { e.preventDefault(); void send(); }}>
          <label htmlFor="agent-message">Ask the Agent</label>
          <textarea id="agent-message" value={draft} onChange={e => setDraft(e.target.value)} rows={3} disabled={busy || active} />
          <div><button type="submit" title="Send: Ask the local Agent." disabled={busy || active || !draft.trim()}><Icon name="send" label="Send" /></button>
            <button type="button" title="New conversation: Clear this chat and keep the editor's settings." disabled={busy || active} onClick={newConversation}><Icon name="chat" label="New conversation" /></button></div>
          <p className="agent-note">The model reads the current editor settings with your message. It remembers about 8,000 words of the
            conversation; older messages drop out, and it says so. Answers have no length limit: Cancel stops one.</p>
        </form> : <div className="agent-empty"><p>Install and deploy a model to chat.</p>
          <ol><li>Press <strong>Check compatibility</strong> on a model to see whether this computer can run it.</li>
            <li><strong>Install</strong> downloads it once (or finds a copy already here) and verifies it.</li>
            <li><strong>Deploy</strong> loads it for a test reply; then the message box appears.</li></ol></div>}
      </div>
    </div>
  </section>;
}
