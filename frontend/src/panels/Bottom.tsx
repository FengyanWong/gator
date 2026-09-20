import { useEffect, useState } from 'react';
import { api, bytes, copy, downloadPackage, Json, num, saveJson } from '../api';
import { usePolling } from '../store';
import { DiffView } from './Editors';

const TABLES = ['evaluations', 'parameters', 'metrics', 'simulator_jobs', 'learner_updates', 'transitions', 'states'];

export function AgentTab({ config, setConfig, request, clearRequest }:
  { config: Json; setConfig: (c: Json) => void; request: { kind: string; selection: Json[] } | null; clearRequest: () => void }) {
  const [settings, setSettings] = useState<Json>(null);
  const [diagnostics, setDiagnostics] = useState<Json>(null);
  const [prompt, setPrompt] = useState('');
  const [kind, setKind] = useState('draft_config');
  const [selection, setSelection] = useState<Json[]>([]);
  const [log, setLog] = useState<Json[]>([]);
  const [proposal, setProposal] = useState<Json>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [manual, setManual] = useState('');
  const [circuitDiff, setCircuitDiff] = useState<Json>(null);
  // Prompt-driven circuit modification: proposal -> structured diff -> confirmation -> WORKING COPY -> reload.
  const circuitChange = async (confirmed: boolean) => {
    try {
      const result = await api.modifyCircuit({ circuit: config.circuit, changes: proposal.circuit_changes, confirmed, output_root: config.output?.output_root ?? null });
      setCircuitDiff(result);
      if (result.applied) say('system', `Working copy written: ${result.working_copy}. The original (${result.original_untouched}) is untouched. ${result.note}`);
    } catch (e) { fail(e); }
  };
  const say = (role: string, text: string, extra?: Json) => setLog(l => [...l, { role, text, extra, at: new Date().toISOString().slice(11, 19) }]);

  useEffect(() => { api.agentSettings().then(setSettings).catch(e => say('error', e.message)); }, []);
  useEffect(() => { if (request) { setKind(request.kind); setSelection(request.selection); clearRequest(); } }, [request]);
  const body = () => ({ kind, prompt, config, selection });
  const fail = (e: any) => say('error', `${e.detail?.code ?? 'error'}: ${e.message}${e.detail?.configuration_unchanged ? ' (your configuration is unchanged)' : ''}`, e.detail);

  const propose = async () => {
    const request_id = crypto.randomUUID().replace(/-/g, '');
    setBusy(request_id); say('user', prompt);
    try { const p = await api.propose({ ...body(), request_id }); setProposal(p); say(p.origin, p.reasoning || '(no reasoning given)', p); }
    catch (e) { fail(e); } finally { setBusy(null); }
  };
  const approveAndApply = async () => {
    try {
      await api.approve({ proposal_id: proposal.proposal_id, proposal_hash: proposal.proposal_hash, config });
      const applied = await api.apply({ proposal_id: proposal.proposal_id, config });
      setConfig(applied.config); setProposal(null); say('system', applied.note);
    } catch (e) { fail(e); setProposal(null); }
  };
  return (
    <div className="agent">
      <div className="agent-side">
        <label>Provider<select value={settings?.provider ?? 'disabled'} onChange={e => api.saveAgentSettings({ ...settings, provider: e.target.value, availability: undefined, note: undefined, cli_path: undefined }).then(() => api.agentSettings().then(setSettings)).catch(fail)}>
          {(settings?.availability ?? []).map((a: Json) => <option key={a.provider} value={a.provider}>{a.provider}{a.available ? '' : ' (CLI not found)'}</option>)}</select></label>
        <label title="Agent model. Independent of the RL model/checkpoint.">Agent model<input value={settings?.model ?? ''} placeholder="CLI default" onChange={e => setSettings({ ...settings, model: e.target.value || null })}
          onBlur={() => api.saveAgentSettings({ provider: settings.provider, model: settings.model, effort: settings.effort, timeout_seconds: settings.timeout_seconds, permission_mode: settings.permission_mode, allowed_tools: settings.allowed_tools, max_turns: settings.max_turns, stream: settings.stream }).catch(fail)} /></label>
        <button onClick={() => api.agentDiagnostics().then(setDiagnostics).catch(fail)}>Diagnostics</button>
        {diagnostics && <details open><summary>Backend environment</summary><pre className="small">{JSON.stringify({ providers: diagnostics.providers, skills: diagnostics.skills.summary, nested: diagnostics.environment.nested_session_note, cwd: diagnostics.environment.cwd }, null, 1)}</pre></details>}
        <p className="hint">Agents prepare proposals only. Applying a configuration, writing a circuit and running a real simulation each need their own authorization. Every manual workflow works without an agent.</p>
      </div>
      <div className="agent-main">
        <div className="chat">{log.map((m, i) => <div key={i} className={`msg ${m.role}`}><span className="who">{m.at} {m.role}</span> {m.text}
          {m.extra?.warnings?.length > 0 && <ul>{m.extra.warnings.map((w: string) => <li key={w} className="warn">warning: {w}</li>)}</ul>}
          {m.extra?.unresolved?.length > 0 && <ul>{m.extra.unresolved.map((w: string) => <li key={w} className="issue unresolved">unresolved: {w}</li>)}</ul>}</div>)}</div>
        {proposal && <div className="confirm"><h4>Proposal from {proposal.origin} - review the diff</h4><DiffView diff={proposal.diff} />
          {proposal.circuit_changes?.length > 0 && <div><h4>Proposed circuit changes ({proposal.circuit_changes.length})</h4>
            <table className="grid small"><tbody>{proposal.circuit_changes.map((c: Json, i: number) => <tr key={i}><td>{c.instance_path}.{c.parameter_name}</td><td>{num(c.new_value)} {c.unit}</td><td>{c.reason}</td></tr>)}</tbody></table>
            {circuitDiff?.diff && <table className="grid small"><thead><tr><th>Parameter</th><th>Before</th><th>After (canonical)</th></tr></thead><tbody>
              {circuitDiff.diff.map((d: Json, i: number) => <tr key={i}><td>{d.instance_path}.{d.parameter_name}</td><td>{num(d.before)} ({d.before_expression})</td><td>{num(d.after)}</td></tr>)}</tbody></table>}
            <button onClick={() => circuitChange(false)}>Preview circuit diff</button>
            <button disabled={!circuitDiff?.diff || circuitDiff.applied} onClick={() => window.confirm('Write a WORKING COPY of the netlist with these changes? The original is never overwritten, and no native schematic is generated.') && circuitChange(true)}>Confirm: write working copy</button>
          </div>}
          <button disabled={!proposal.diff.length} onClick={approveAndApply}>Approve and apply to the configuration</button>
          <button onClick={() => api.reject(proposal.proposal_id).then(() => setProposal(null))}>Reject</button>
          <span className="hint"> The approval is bound to this exact proposal, configuration and circuit; any later change invalidates it.</span></div>}
        <div className="row">
          <select value={kind} onChange={e => setKind(e.target.value)}>{['draft_config', 'parameters', 'targets', 'measurements', 'modify_fields', 'circuit_modification'].map(k => <option key={k}>{k}</option>)}</select>
          {kind === 'modify_fields' && <span className="hint">{selection.length} selected row(s)</span>}
        </div>
        <textarea value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Describe what you need. State where each requirement comes from; the agent may not invent requirements." rows={3} />
        <div className="row">
          <button disabled={!prompt.trim() || !!busy || settings?.provider === 'disabled'} onClick={propose}>Ask agent for a proposal</button>
          {busy && <button onClick={() => api.cancelAgent(busy)}>Cancel request</button>}
          <button disabled={!prompt.trim()} onClick={() => api.exportTask(body()).then(t => saveJson('agent_task.json', t)).catch(fail)}>Export task description</button>
        </div>
        <details><summary>Import a structured result (manual workflow)</summary>
          <textarea value={manual} onChange={e => setManual(e.target.value)} rows={3} placeholder="Paste the JSON object returned by any assistant" />
          <button disabled={!manual.trim() || !prompt.trim()} onClick={() => { try { api.importResult({ ...body(), result: JSON.parse(manual) }).then(p => { setProposal(p); say(p.origin, p.reasoning, p); }).catch(fail); } catch (e: any) { say('error', 'Not valid JSON: ' + e.message); } }}>Validate and show diff</button></details>
      </div>
    </div>
  );
}

export function StatusTab({ status, onCommand, onContinue }: { status: Json; onCommand: (c: string) => void; onContinue: () => void }) {
  if (!status) return <p className="hint">No run selected.</p>;
  const b = status.budget, best = status.best_design, first = status.first_feasible, conn = status.connection;
  return (<div className="status-grid">
    {status.manifest?.mock && <p className="mock">{status.manifest.mock_notice}</p>}
    <table className="grid small"><tbody>
      <tr><td>State</td><td><b>{status.state}</b>{status.stop_reason ? ` (${status.stop_reason})` : ''}{status.worker_alive ? ' - worker alive' : ''}</td></tr>
      <tr><td>Mode / model</td><td>{status.mode} {status.manifest?.source_model?.run_id ? `from ${status.manifest.source_model.run_id.slice(0, 12)} / ${status.manifest.source_model.checkpoint_id}` : '(no weights loaded)'}</td></tr>
      <tr><td>Budget</td><td>{b ? `${b.charged} charged / ${b.max_evaluations}  (in flight ${b.in_flight}, completed ${b.completed}, failed ${b.failed}, remaining ${b.remaining})` : '-'}</td></tr>
      <tr><td>Spectre launches</td><td>{b ? `${b.launches}${b.max_launches ? ' / ' + b.max_launches : ''}  (retries ${b.retries}, cache hits ${b.cache_hits})` : '-'}</td></tr>
      <tr><td>Active workers</td><td>{(status.active_workers ?? []).map((w: Json) => `#${w.worker_id}: ${w.phase} attempt ${w.attempt}`).join('; ') || 'none'} (concurrency {status.concurrency})</td></tr>
      <tr><td>Learner updates</td><td>{status.learner_updates}</td></tr>
      <tr><td>First feasibility</td><td>{first ? `at ${first.first_feasible_eval_count} evaluations charged (dispatch #${first.dispatch_index}, ${first.completed_count} completed, ${first.in_flight_count} in flight, ${first.spectre_launches} launches)` : 'not yet (null)'}</td></tr>
      <tr><td>Best design</td><td>{best ? `${best.feasible ? 'FEASIBLE' : 'infeasible'}  ${Object.entries(best.metrics).map(([k, v]) => `${k}=${num(v)}`).join(' ')}  violation ${num(best.violation)}` : 'none'}</td></tr>
      <tr><td>Connection</td><td><span className={`badge state-${conn?.overall}`}>{conn?.overall}</span>{conn?.age_seconds != null && ` ${Math.round(conn.age_seconds)} s old`}</td></tr>
      <tr><td>Persistence</td><td className={status.persistence?.failed ? 'error' : ''}>{status.persistence ? `commit ${status.persistence.last_commit_seq}, flushed ${status.persistence.flushed_seq}, ${bytes(status.persistence.bytes_written)} table data; last save ${status.persistence.last_successful_save ?? '-'}` : '-'} {status.persistence?.failed ?? ''}</td></tr>
      <tr><td>Last checkpoint</td><td>{status.last_checkpoint_utc ?? '-'}</td></tr>
      <tr><td>Run directory</td><td className="path" onClick={() => copy(status.run_dir)}>{status.run_dir}</td></tr>
      {status.error && <tr><td>Error</td><td className="error">{status.error}</td></tr>}
    </tbody></table>
    <div className="row">
      <button disabled={!status.worker_alive} onClick={() => onCommand('pause')}>Pause and save</button>
      <button disabled={!status.worker_alive} onClick={() => onCommand('stop')}>Stop and save</button>
      <button disabled={!status.worker_alive} onClick={() => onCommand('cancel')} title="Forced: unfinished evaluations are recorded as cancelled and stay charged.">Force cancel</button>
      <button disabled={status.worker_alive || !['paused', 'stopped', 'interrupted'].includes(status.state)} onClick={onContinue}>Continue</button>
    </div>
  </div>);
}

export function DataTab({ runDir }: { runDir: string | null }) {
  const [table, setTable] = useState('evaluations');
  const [data, setData] = useState<Json>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => { if (runDir) api.table(runDir, table).then(setData).catch(e => setNote(e.message)); else setData(null); }, [runDir, table]);
  if (!runDir) return <p className="hint">No run selected.</p>;
  return (<div>
    <div className="row"><select value={table} onChange={e => setTable(e.target.value)}>{TABLES.map(t => <option key={t}>{t}</option>)}</select>
      <button onClick={() => api.table(runDir, table).then(setData)}>Refresh</button>
      <button onClick={() => api.exportCsv(runDir, table).then(r => setNote(`CSV written: ${r.path}`)).catch(e => setNote(e.message))}>Export detailed CSV</button>
      <button onClick={() => api.exportAggregates(runDir).then(r => setNote(`Aggregates: ${r.experiment_dir}/aggregates`)).catch(e => setNote(e.message))}>Export research CSVs</button>
      <span className="hint">{data ? `${data.total_rows} rows (snapshot at commit ${data.cutoff_commit_seq}); last ${data.rows.length} shown` : ''} {note}</span></div>
    {data && <div className="scroll"><table className="grid small"><thead><tr>{data.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{data.rows.map((r: Json, i: number) => <tr key={i}>{data.columns.map((c: string) => <td key={c}>{typeof r[c] === 'object' && r[c] !== null ? JSON.stringify(r[c]) : num(r[c])}</td>)}</tr>)}</tbody></table></div>}
  </div>);
}

export function FilesTab({ runDir }: { runDir: string | null }) {
  const [files, setFiles] = useState<Json>(null);
  const refresh = () => runDir && api.files(runDir).then(setFiles);
  useEffect(() => { refresh(); }, [runDir]);
  if (!runDir) return <p className="hint">No run selected.</p>;
  return (<div><div className="row"><button onClick={refresh}>Refresh</button><button onClick={() => downloadPackage(runDir)}>Download data-only package (.zip)</button>
    <button onClick={() => copy(runDir)}>Copy run path</button><span className="hint">{files && `${files.files.length} files, ${bytes(files.total_bytes)}`} "Open local folder" is not offered: no desktop integration is available from a browser.</span></div>
    <div className="scroll"><table className="grid small"><thead><tr><th>File</th><th>Size</th><th>Modified (UTC)</th><th></th></tr></thead>
      <tbody>{files?.files.map((f: Json) => <tr key={f.path}><td>{f.path}</td><td>{bytes(f.bytes)}</td><td>{f.modified_utc.slice(0, 19)}</td><td><a href={api.downloadUrl(runDir, f.path)}>download</a></td></tr>)}</tbody></table></div></div>);
}

export function LogsTab({ runDir, alive }: { runDir: string | null; alive: boolean }) {
  const [kind, setKind] = useState('events');
  const { value } = usePolling(() => api.logs(runDir!, kind), alive ? 2000 : 60000, !!runDir, [runDir, kind]);
  if (!runDir) return <p className="hint">No run selected.</p>;
  return (<div><div className="row"><select value={kind} onChange={e => setKind(e.target.value)}><option>events</option><option>errors</option></select></div>
    <div className="scroll log">{(value?.entries ?? []).slice().reverse().map((e: Json, i: number) => <div key={i} className={kind === 'errors' ? 'error' : ''}>
      <b>{(e.time_utc ?? '').slice(11, 19)} {e.event ?? e.error}</b> {JSON.stringify(Object.fromEntries(Object.entries(e).filter(([k]) => !['time_utc', 'event', 'error', 'run_id', 'traceback'].includes(k))))}</div>)}</div></div>);
}
