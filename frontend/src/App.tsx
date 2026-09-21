import { useEffect, useRef, useState } from 'react';
import { api, Json } from './api';
import { useConfig, usePolling } from './store';
import { CircuitPanel } from './panels/Left';
import { ConnectionButton } from './panels/Connection';
import { Editors } from './panels/Editors';
import { ValidationStatus } from './panels/Issues';
import { LIVE_STATES, RunButtons, launchWithConsent, resumeRun, useRunControl } from './panels/RunControl';
import { RunListButton } from './panels/RunList';
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
  const [runDir, setRunDir] = useState<string | null>(() => { try { return localStorage.getItem('gator-workbench-current-run-v1') || null; } catch { return null; } });
  const [tab, setTab] = useState<BottomTab>('status');
  const [agentRequest, setAgentRequest] = useState<{ kind: string; selection: Json[]; prompt?: string } | null>(null);
  const [agentTabSlot, setAgentTabSlot] = useState<HTMLElement | null>(null);      // on the tab itself: where AgentTab puts its pop-out control
  const [agentDetached, setAgentDetached] = useState(false);
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
  const refreshRuns = (): Promise<Json[]> => api.runs(config.output.output_root ?? undefined).then(r => { setRuns(r.runs); return r.runs; }).catch(() => { setRuns([]); return []; });

  // Static validation follows every edit (debounced); it never starts anything.
  useEffect(() => {
    const id = setTimeout(() => api.validate(config).then(setValidation).catch(e => setValidation({ blocks_run: true, issues: [{ level: 'error', code: 'schema', path: '', message: e.message + ' ' + JSON.stringify(e.detail?.errors ?? '') }], facts: {} })), 500);
    return () => clearTimeout(id);
  }, [JSON.stringify(config)]);

  const { value: status } = usePolling(() => api.status(runDir!), 1500, !!runDir, [runDir]);
  const isReal = circuit?.loaded && circuit.mock === false;
  // The run the header buttons act on (Start -> Pause -> Resume, Abort). It is not the run the bottom tabs show.
  const [looked, setLooked] = useState(false);
  const control = useRunControl(status, looked);
  const adopted = useRef(false);
  useEffect(() => {
    refreshRuns().then(list => {
      // Once, when the page opens: a run that is live although this page does not hold it (started from another browser or
      // the CLI, or the browser's memory was cleared) is taken over, so the header offers Pause and Abort, not a second Start.
      if (adopted.current) return;
      adopted.current = true;
      const isLive = (r: Json) => LIVE_STATES.includes(r.state);
      const running = list.some(r => r.run_dir === control.dir && isLive(r)) ? null : list.find(isLive);
      if (running) { control.take(running.run_dir); setRunDir(running.run_dir); }
      setLooked(true);
    });
  }, [config.output.output_root]);

  const showRun = (started: Json, as: 'start' | 'resume') => {
    setRunDir(started.run_dir); setTab('status'); refreshRuns();
    setMessage(as === 'resume' ? { level: 'info', text: `Continuing in the original run directory: ${started.run_dir}` }
      : { level: started.mock ? 'mock' : 'info', text: `${started.mock ? started.mock_notice + ' ' : ''}Run directory: ${started.run_dir}` });
  };
  const launchedRun = (started: Json, as: 'start' | 'resume') => { control.take(started.run_dir, as); showRun(started, as); };
  const failed = (e: any) => setMessage({ level: 'error', text: `${e.detail?.code ?? 'rejected'}: ${e.message}`, detail: e.detail });
  const start = async (baseline_only: boolean) => {
    setMessage(null);
    const budget = baseline_only ? 1 : config.run.max_evaluations;
    control.setPending('start');
    try {
      // A refusal creates nothing; what the backend asks for (real budget, a model from another task, unknown
      // connection layers) is put to the user and the start is repeated with the answers.
      const started = await launchWithConsent(flags => api.start({ config, baseline_only, ...flags }), { real: !!isReal, transfer: true,
        authorizeText: `This starts REAL Virtuoso/Spectre simulations.\nAuthorize a budget of ${budget} candidate evaluation(s)?` });
      if (started) launchedRun(started, 'start'); else setMessage({ level: 'info', text: 'Not started: you answered no, so nothing was created.' });
    } catch (e: any) { failed(e); } finally { control.setPending(null); }
  };
  // "Continue" of the Run status tab: the run shown there, with the question about a new total budget.
  const continueRun = async () => {
    if (!runDir) return;
    const extra = window.prompt('Continue this run. New total evaluation budget (empty = unchanged):', '');
    if (extra === null) return;
    try {
      const started = await resumeRun(runDir, status?.run_dir === runDir ? status : null, Number(extra) >= 1 ? Math.floor(Number(extra)) : null);
      if (!started) return;
      // It becomes the header's run too, unless the header is busy with another live run.
      if (control.dir === runDir || control.phase === 'idle' || control.phase === 'paused') launchedRun(started, 'resume');
      else { refreshRuns(); setMessage({ level: 'info', text: `Continuing in the original run directory: ${started.run_dir}` }); }
    } catch (e: any) { failed(e); }
  };
  const sendCommand = (name: string) => runDir && api.command(runDir, name).then(() => control.refresh()).catch(failed);

  if (fatal) return <p className="error">Backend not reachable: {fatal}</p>;
  if (!schema) return <p>Loading schema...</p>;
  return (
    <div className="layout">
      <header>
        <b>GATOR workbench</b><span className="hint"> {meta?.version} | {meta?.environment?.environment} | data-only outputs (no plots)</span>
        <span className="spacer" />
        <ValidationStatus validation={validation} config={config} schema={schema} />
        <button onClick={() => api.validate(config).then(setValidation)}>Static validation</button>
        <button disabled={!!validation?.blocks_run || control.phase !== 'idle'} onClick={() => start(true)}
          title={control.phase === 'idle' ? 'ONE costed evaluation of the initial design. It is a preflight record, not free.' : 'Not while the header holds a run that is active or paused. Abort lets go of a paused run.'}>Single baseline simulation</button>
        <RunButtons control={control} blocked={!!validation?.blocks_run} onStart={() => start(false)} onResumed={started => showRun(started, 'resume')}
          onMessage={setMessage} onShow={dir => { setRunDir(dir); setTab('status'); }} />
      </header>
      {message && <div className={`banner ${message.level}`} onClick={() => setMessage(null)}>{message.text}
        {message.detail?.report && <details><summary>details</summary><pre>{JSON.stringify(message.detail.report, null, 1)}</pre></details>}</div>}
      <aside className="left">
        <ConnectionButton profileId={profileId} setProfileId={id => setConfig((c: Json) => ({ ...c, run: { ...c.run, connection_profile_id: id } }))} />
        <CircuitPanel config={config} setConfig={setConfig} circuit={circuit} setCircuit={setCircuit} profileId={profileId} meta={meta}
          onAgent={(kind, selection, prompt) => { setAgentRequest({ kind, selection, prompt }); setTab('agent'); }} />
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
          {/* The agent tab carries a small control at its right end, where a browser tab has its close button: it moves the
              conversation into a window of its own. Two sibling buttons in one tab shape - a button inside a button is not valid. */}
          <span className={`tab-group${tab === 'agent' ? ' active' : ''}${agentDetached ? ' detached' : ''}`}>
            <button onClick={() => setTab('agent')}>Agent</button><span className="tab-slot" ref={setAgentTabSlot} /></span>
          {(['status', 'logs', 'data', 'files'] as Exclude<BottomTab, 'agent'>[]).map(t => <button key={t} className={t === tab ? 'active' : ''} onClick={() => setTab(t)}>
            {{ status: 'Run status', logs: 'Logs', data: 'Data tables', files: 'Output files' }[t]}</button>)}
          <span className="spacer" />
          <RunListButton runs={runs} runDir={runDir} onChoose={setRunDir} onRefresh={refreshRuns} />
        </div>
        <div className="bottom-body">
          <AgentTab hidden={tab !== 'agent'} config={config} setConfig={setConfig} request={agentRequest} clearRequest={() => setAgentRequest(null)}
            tabSlot={agentTabSlot} onDetached={setAgentDetached} runDir={runDir} />
          {tab === 'status' && <StatusTab status={status} onCommand={sendCommand} onContinue={continueRun} />}
          {tab === 'logs' && <LogsTab runDir={runDir} alive={!!status?.worker_alive} />}
          {tab === 'data' && <DataTab runDir={runDir} />}
          {tab === 'files' && <FilesTab runDir={runDir} />}
        </div>
      </footer>
    </div>
  );
}
