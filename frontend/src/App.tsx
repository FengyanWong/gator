import { useEffect, useState } from 'react';
import { api, Json } from './api';
import { useConfig, usePolling } from './store';
import { CircuitPanel, ConnectionPanel } from './panels/Left';
import { Editors } from './panels/Editors';
import { OutputPanel, ResearchPanel, RunPanel } from './panels/Right';
import { AgentTab, DataTab, FilesTab, LogsTab, StatusTab } from './panels/Bottom';

type BottomTab = 'agent' | 'status' | 'logs' | 'data' | 'files';

/** Layout (specification section 2): left = project, connection, circuit; center = three editors;
 *  right = run configuration + output settings (always visible); bottom = agent, logs, status, data, files.
 *  Tables, numbers, status and file lists only - nothing is plotted. */
export function App() {
  const store = useConfig();
  const { config, setConfig } = store;
  const [schema, setSchema] = useState<Json>(null);
  const [meta, setMeta] = useState<Json>(null);
  const [circuit, setCircuit] = useState<Json>(null);
  const [validation, setValidation] = useState<Json>(null);
  const [runs, setRuns] = useState<Json[]>([]);
  const [runDir, setRunDir] = useState<string | null>(null);
  const [tab, setTab] = useState<BottomTab>('status');
  const [agentRequest, setAgentRequest] = useState<{ kind: string; selection: Json[] } | null>(null);
  const [message, setMessage] = useState<Json>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const profileId: string | null = config.run.connection_profile_id ?? null;

  useEffect(() => {
    Promise.all([api.schema(), api.meta()]).then(([s, m]) => {
      setSchema(s); setMeta(m);
      // Restore the previous concurrency on a fresh browser (default 1 when none was ever used).
      const remembered = m.remembered?.concurrency;
      if (remembered && !localStorage.getItem('gator-workbench-config-v1')) setConfig((c: Json) => ({ ...c, run: { ...c.run, concurrency: remembered } }), false);
    }).catch(e => setFatal(e.message));
  }, []);
  const refreshRuns = () => api.runs(config.output.output_root ?? undefined).then(r => setRuns(r.runs)).catch(() => setRuns([]));
  useEffect(() => { refreshRuns(); }, [config.output.output_root]);

  // Static validation follows every edit (debounced); it never starts anything.
  useEffect(() => {
    const id = setTimeout(() => api.validate(config).then(setValidation).catch(e => setValidation({ blocks_run: true, issues: [{ level: 'error', code: 'schema', path: '', message: e.message + ' ' + JSON.stringify(e.detail?.errors ?? '') }], facts: {} })), 500);
    return () => clearTimeout(id);
  }, [JSON.stringify(config)]);

  const { value: status } = usePolling(() => api.status(runDir!), 1500, !!runDir, [runDir]);
  const isReal = circuit?.loaded && circuit.mock === false;

  const start = async (baseline_only: boolean) => {
    setMessage(null);
    const body: Json = { config, baseline_only };
    if (isReal) {
      const budget = baseline_only ? 1 : config.run.max_evaluations;
      if (!window.confirm(`This starts REAL Virtuoso/Spectre simulations.\nAuthorize a budget of ${budget} candidate evaluation(s)?`)) return;
      body.authorize_real_simulation = true;
    }
    try {
      const started = await api.start(body);
      setRunDir(started.run_dir); setTab('status'); refreshRuns();
      setMessage({ level: started.mock ? 'mock' : 'info', text: `${started.mock ? started.mock_notice + ' ' : ''}Run directory: ${started.run_dir}` });
    } catch (e: any) {
      const detail = e.detail ?? {};
      if (detail.code === 'confirm_transfer' && window.confirm(`${detail.report?.reason}\n\nLoad this model for a NEW task (fine_tune creates a new run with a parent)?`)) {
        try { const started = await api.start({ ...body, confirm_transfer: true }); setRunDir(started.run_dir); refreshRuns(); return; } catch (again: any) { setMessage({ level: 'error', text: again.message, detail: again.detail }); return; }
      }
      if (detail.code === 'connection_gate_acknowledge' && window.confirm(`Connection layers are UNKNOWN: ${detail.report?.uncertain?.join(', ')}.\nUnknown is not OK. Proceed anyway?`)) {
        try { const started = await api.start({ ...body, acknowledge_unknown_connection: true }); setRunDir(started.run_dir); refreshRuns(); return; } catch (again: any) { setMessage({ level: 'error', text: again.message, detail: again.detail }); return; }
      }
      setMessage({ level: 'error', text: `${detail.code ?? 'rejected'}: ${e.message}`, detail });
    }
  };
  const continueRun = async () => {
    if (!runDir) return;
    const extra = window.prompt('Continue this run. New total evaluation budget (empty = unchanged):', '');
    try { await api.continueRun({ run_dir: runDir, max_evaluations: extra ? Number(extra) : null, authorize_real_simulation: isReal }); setMessage({ level: 'info', text: 'Continuing in the original run directory.' }); }
    catch (e: any) { setMessage({ level: 'error', text: `${e.detail?.code ?? ''}: ${e.message}`, detail: e.detail }); }
  };

  if (fatal) return <p className="error">Backend not reachable: {fatal}</p>;
  if (!schema) return <p>Loading schema...</p>;
  const blocking = (validation?.issues ?? []).filter((i: Json) => i.level === 'error' || i.level === 'blocker');
  return (
    <div className="layout">
      <header>
        <b>GATOR workbench</b><span className="hint"> {meta?.version} | {meta?.environment?.environment} | data-only outputs (no plots)</span>
        <span className="spacer" />
        <span className={validation?.blocks_run ? 'error' : 'ok'}>{validation ? (validation.blocks_run ? `${blocking.length} blocking issue(s)` : 'configuration valid') : 'validating...'}</span>
        <button onClick={() => api.validate(config).then(setValidation)}>Static validation</button>
        <button disabled={!!validation?.blocks_run} onClick={() => start(true)} title="ONE costed evaluation of the initial design. It is a preflight record, not free.">Single baseline simulation</button>
        <button className="primary" disabled={!!validation?.blocks_run} onClick={() => start(false)}>Start</button>
      </header>
      {message && <div className={`banner ${message.level}`} onClick={() => setMessage(null)}>{message.text}
        {message.detail?.report && <details><summary>details</summary><pre>{JSON.stringify(message.detail.report, null, 1)}</pre></details>}</div>}
      <aside className="left">
        <ConnectionPanel profileId={profileId} setProfileId={id => setConfig((c: Json) => ({ ...c, run: { ...c.run, connection_profile_id: id } }))} />
        <CircuitPanel config={config} setConfig={setConfig} circuit={circuit} setCircuit={setCircuit} profileId={profileId} />
      </aside>
      <main>
        <Editors schema={schema} config={config} setConfig={setConfig} undo={store.undo} redo={store.redo} canUndo={store.canUndo} canRedo={store.canRedo}
          save={store.save} savedAt={store.savedAt} validation={validation} onAgent={(kind, selection) => { setAgentRequest({ kind, selection }); setTab('agent'); }} />
      </main>
      <aside className="right">
        <RunPanel config={config} setConfig={setConfig} runs={runs} circuit={circuit} />
        <OutputPanel config={config} setConfig={setConfig} meta={meta} activeRun={status} />
        <ResearchPanel config={config} setConfig={setConfig} />
      </aside>
      <footer>
        <div className="tabs">
          {(['agent', 'status', 'logs', 'data', 'files'] as BottomTab[]).map(t => <button key={t} className={t === tab ? 'active' : ''} onClick={() => setTab(t)}>
            {{ agent: 'Agent conversation', status: 'Run status', logs: 'Logs', data: 'Data tables', files: 'Output files' }[t]}</button>)}
          <span className="spacer" />
          <select value={runDir ?? ''} onChange={e => setRunDir(e.target.value || null)} onFocus={refreshRuns}>
            <option value="">(select a run)</option>
            {runs.map(r => <option key={r.run_dir} value={r.run_dir}>{r.created_utc?.slice(0, 19)} | {r.task_id} | {r.mode} seed{r.seed} | {r.state}{r.mock ? ' [MOCK]' : ''}</option>)}</select>
        </div>
        <div className="bottom-body">
          {tab === 'agent' && <AgentTab config={config} setConfig={setConfig} request={agentRequest} clearRequest={() => setAgentRequest(null)} />}
          {tab === 'status' && <StatusTab status={status} onCommand={c => runDir && api.command(runDir, c)} onContinue={continueRun} />}
          {tab === 'logs' && <LogsTab runDir={runDir} alive={!!status?.worker_alive} />}
          {tab === 'data' && <DataTab runDir={runDir} />}
          {tab === 'files' && <FilesTab runDir={runDir} />}
        </div>
      </footer>
    </div>
  );
}
