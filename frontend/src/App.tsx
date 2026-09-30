import { useEffect, useRef, useState } from 'react';
import { api, ApiError, Json, NO_ANSWER, plainError } from './api';
import { useConfig, usePolling, useRequest } from './store';
import { CircuitPanel } from './panels/Left';
import { ConnectionButton } from './panels/Connection';
import { CheckSteps } from './panels/Consistency';
import { Editors } from './panels/Editors';
import { ValidationStatus } from './panels/Issues';
import { LIVE_STATES, RunButtons, launchWithConsent, resumeRun, useRunControl } from './panels/RunControl';
import { RunListButton } from './panels/RunList';
import { OutputPanel, ResearchPanel, RunPanel } from './panels/Right';
import { AgentTab } from './panels/AgentTab';
import { DataTab, FilesTab, LogsTab, StatusTab } from './panels/RunTabs';
import { CornerCheckTab } from './panels/CornerCheck';

type BottomTab = 'agent' | 'status' | 'logs' | 'data' | 'files' | 'corners';

/** A configuration the backend cannot even read (HTTP 422): one blocking issue per field it names, in its plain words
 *  (schema.describe_errors), at the place the validation report uses (parameters[1].variable_id), so the list names the
 *  row and the editor marks it. Before, all of them were one issue with pydantic's list as JSON (user report 2026-09-21).
 *  An older backend sends parameters.1.variable_id and pydantic's text: the path is rewritten the same way. Anything
 *  else (the backend unreachable...) stays one issue. */
function rejected(e: any): Json {
  const errors: Json[] = Array.isArray(e.detail?.errors) ? e.detail.errors : [];
  const issues = errors.length ? errors.map((x: Json) => ({ level: 'error', code: x.code ?? 'schema', message: x.message, technical: x.technical,
    path: String(x.path ?? '').replace(/\.(\d+)(?=\.|$)/g, '[$1]') }))
    : [e instanceof ApiError ? { level: 'error', code: 'schema', path: '', message: e.message } : { level: 'error', code: 'no_answer', path: '', message: NO_ANSWER }];
  return { blocks_run: true, issues, facts: {} };
}
const NO_RUNS: Json[] = [];                          // one empty list: a failed read does not make the model list read again

/** Layout (specification section 2): left = project, connection, circuit; center = three editors;
 *  right = run configuration + output settings (always visible); bottom = agent, logs, status, data, files.
 *  Tables, numbers, status and file lists only - nothing is plotted. */
export function App() {
  const store = useConfig();
  const { config, setConfig } = store;
  const [schema, setSchema] = useState<Json>(null);
  const [meta, setMeta] = useState<Json>(null);
  const [circuit, setCircuit] = useState<Json>(null);
  const [runs, setRuns] = useState<Json[]>(NO_RUNS);
  const [runsError, setRunsError] = useState<string | null>(null);   // the run list could not be read: said, not shown as "no run yet"
  const [continuing, setContinuing] = useState(false);
  const [runDir, setRunDir] = useState<string | null>(() => { try { return localStorage.getItem('gator-workbench-current-run-v1') || null; } catch { return null; } });
  const [tab, setTab] = useState<BottomTab>('status');
  const [agentRequest, setAgentRequest] = useState<{ kind: string; selection: Json[]; prompt?: string } | null>(null);
  const [agentTabSlot, setAgentTabSlot] = useState<HTMLElement | null>(null);      // on the tab itself: where AgentTab puts its pop-out control
  const [taskSlot, setTaskSlot] = useState<HTMLElement | null>(null);              // editors' tab line: where the circuit panel puts "Save task"
  const [taskNotes, setTaskNotes] = useState<HTMLElement | null>(null);            // under the editors' toolbar: its messages and questions
  const [agentDetached, setAgentDetached] = useState(false);
  const [message, setMessage] = useState<Json>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const profileId: string | null = config.run.connection_profile_id ?? null;

  useEffect(() => {
    Promise.all([api.schema(), api.meta()]).then(([s, m]) => {
      setSchema(s); setMeta(m);
      // Restore the previous concurrency on a fresh browser (default 1 when none was ever used). Blocked site storage
      // counts as a fresh browser: the page then starts from the default configuration too (useConfig).
      // "Fresh" is decided when the page opens (the 0.8 s autosave may have written the default configuration by now).
      const remembered = m.remembered?.concurrency;
      if (remembered && store.fresh) setConfig((c: Json) => ({ ...c, run: { ...c.run, concurrency: remembered } }), false);
    }).catch(e => setFatal(e.message));
  }, []);
  // Only the newest read of the run list may answer: while the output root is typed, a half-typed path outside the roots
  // (403) used to empty the list when its answer came last.
  const listing = useRef(0);
  const refreshRuns = (): Promise<Json[]> => {
    const mine = ++listing.current;
    return api.runs(config.output.output_root ?? undefined).then(r => ({ list: r.runs as Json[], error: null }), e => ({ list: NO_RUNS, error: plainError(e) }))
      .then(({ list, error }) => { if (mine === listing.current) { setRuns(list); setRunsError(error); } return list; });
  };

  // Debounce validation and ignore replies for a configuration that has since changed. `sent`: the configuration the
  // report is about - its row paths (targets[3]) name rows of THAT configuration, which Delete, Undo or Import may have
  // moved by the time it is drawn (the editors check the row before they mark it).
  const { value: validation } = useRequest<Json>(() => api.validate(config).catch(rejected).then(v => ({ ...v, sent: config })), [JSON.stringify(config)],
    { delay: 500, keepPrevious: true });

  // A run that has ended for good (completed, failed, cancelled: none of them can be continued) changes no more, so its
  // status is read once a minute instead of every 1.5 s. A paused or stopped run can come back, and keeps the quick poll.
  const [statusEvery, setStatusEvery] = useState(1500);
  // The run shown is gone (deleted, or outside the allowed roots by now - it may be the remembered one the page opened
  // with): it is let go, as the header lets go of its own, instead of being asked for every 1.5 s for ever while the strip
  // still names its folder. Two answers in a row: on the 9p-mounted D: drive a stat right after a rename can fail once,
  // and one 404 of a run that is there must not take it off the page.
  const gone = useRef(0);
  useEffect(() => { gone.current = 0; }, [runDir]);
  const readStatus = (dir: string) => api.status(dir).then(value => { gone.current = 0; return value; }, e => {
    if (e instanceof ApiError && (e.status === 403 || e.status === 404) && ++gone.current >= 2) setRunDir(shown => (shown === dir ? null : shown));
    throw e;
  });
  const { value: polledStatus, error: statusError } = usePolling(() => readStatus(runDir!), statusEvery, !!runDir, [runDir]);
  const status = polledStatus?.run_dir === runDir ? polledStatus : null;
  useEffect(() => setStatusEvery(status && !status.worker_alive && ['completed', 'failed', 'cancelled'].includes(status.state) ? 60000 : 1500),
    [status?.worker_alive, status?.state]);
  const isReal = circuit?.loaded && circuit.mock === false;
  // The run the header buttons act on (Start -> Pause -> Resume, Abort). It is not the run the bottom tabs show.
  const [looked, setLooked] = useState(false);
  const control = useRunControl(status, looked);
  // When the header's run comes to rest, the Project column reads its task again (a finished Single baseline simulation
  // records the task's reference by itself, status record 7.78): a counter the column follows. Not on the page's first look,
  // and not after a start that never ran (refused or declined) or a paused run let go: nothing about the task changed.
  const [taskEpoch, setTaskEpoch] = useState(0);
  const lastPhase = useRef(control.phase);
  useEffect(() => {
    if (control.phase === 'idle' && ['running', 'pausing', 'aborting', 'finishing'].includes(lastPhase.current)) setTaskEpoch(n => n + 1);
    lastPhase.current = control.phase;
  }, [control.phase]);
  const adopted = useRef(false);
  useEffect(() => {
    // The list follows the output root while it is typed: read 0.5 s after the last keystroke, not once per key (each read
    // looks at every run under the root). The first read, when the page opens, goes at once.
    const timer = setTimeout(() => refreshRuns().then(list => {
      // Once, when the page opens: a run that is live although this page does not hold it (started from another browser or
      // the CLI, or the browser's memory was cleared) is taken over, so the header offers Pause and Abort, not a second Start.
      if (adopted.current) return;
      adopted.current = true;
      const isLive = (r: Json) => LIVE_STATES.includes(r.state);
      const running = list.some(r => r.run_dir === control.dir && isLive(r)) ? null : list.find(isLive);
      if (running) { control.take(running.run_dir); setRunDir(running.run_dir); }
      setLooked(true);
    }), adopted.current ? 500 : 0);
    return () => clearTimeout(timer);
  }, [config.output.output_root]);

  const showRun = (started: Json, as: 'start' | 'resume') => {
    setRunDir(started.run_dir); setTab('status'); refreshRuns();
    setMessage(as === 'resume' ? { level: 'info', text: `Continuing in the original run directory: ${started.run_dir}` }
      : { level: started.mock ? 'mock' : 'info', text: `${started.mock ? started.mock_notice + ' ' : ''}Run directory: ${started.run_dir}` });
  };
  const launchedRun = (started: Json, as: 'start' | 'resume') => { control.take(started.run_dir, as); showRun(started, as); };
  const failed = (e: any) => setMessage({ level: 'error', text: plainError(e), detail: e.detail });
  const start = async (baseline_only: boolean) => {
    setMessage(null);
    const budget = baseline_only ? 1 : config.run.max_evaluations;
    const search = config.run.search;
    const llm = !baseline_only && !!search && search.method !== 'sac';
    const llmText = llm ? `\nAI sizing: up to ${search.max_llm_calls ?? 'unset'} model calls${search.max_llm_notional_usd != null ? `, notional cost ceiling $${search.max_llm_notional_usd}` : ' (no reported dollar cost for Codex)'}.` : '';
    control.setPending('start');
    try {
      // A refusal creates nothing; what the backend asks for (real budget, a model from another task, unknown
      // connection layers) is put to the user and the start is repeated with the answers.
      // An ngspice netlist task is real too (circuit simulations, counted and recorded as such), only without a license.
      const started = await launchWithConsent(flags => api.start({ config, baseline_only, ...flags }), { real: !!isReal, transfer: true, llm,
        authorizeText: (!isReal ? `Start ${budget} synthetic MOCK evaluations?` : circuit?.simulator === 'ngspice' ? `This starts ngspice simulations of the task (no license; every one is counted as a real evaluation).\nRun a budget of ${budget} candidate evaluation(s)?`
          : `This starts REAL Virtuoso/Spectre simulations.\nAuthorize a budget of ${budget} candidate evaluation(s)?`) + llmText });
      if (started) launchedRun(started, 'start'); else setMessage({ level: 'info', text: 'Not started: you answered no, so nothing was created.' });
    } catch (e: any) { failed(e); } finally { control.setPending(null); }
  };
  // "Continue" of the Run status tab: the run shown there, with the question about a new total budget.
  // While it is on its way (seconds: the check before every run may ask Virtuoso) Continue - and the header's Resume of
  // the same run - wait: a second press repeated both questions and then failed with "already running".
  const continueRun = async () => {
    if (!runDir || continuing) return;
    const extra = window.prompt('Continue this run. New total evaluation budget (empty = unchanged):', '');
    if (extra === null) return;
    const held = control.dir === runDir;
    setContinuing(true); if (held) control.setPending('resume');
    try {
      const started = await resumeRun(runDir, status?.run_dir === runDir ? status : null, Number(extra) >= 1 ? Math.floor(Number(extra)) : null);
      if (!started) return;
      // It becomes the header's run too, unless the header is busy with another live run.
      if (control.dir === runDir || control.phase === 'idle' || control.phase === 'paused') launchedRun(started, 'resume');
      else { refreshRuns(); setMessage({ level: 'info', text: `Continuing in the original run directory: ${started.run_dir}` }); }
    } catch (e: any) { failed(e); } finally { setContinuing(false); if (held) control.setPending(null); }
  };
  // ...but not while the header is busy with ANOTHER run (the case above that does not hand the run to the header): the
  // continued run would have no Pause or Abort anywhere - the tab's run buttons went on 2026-09-29 - and two real runs
  // would drive the one Virtuoso session. A paused run there is no hindrance: the header takes the continued run instead.
  const continueBlocked: string | null = continuing ? 'The run is being continued; a moment.'
    : control.dir === runDir || control.phase === 'idle' || control.phase === 'paused' ? null
    : control.phase === 'checking' ? 'The header is still looking up which run is live; a moment.'
    : 'Another run is live in the header: pause it or let it finish first (a second live run would have no Pause or Abort on this page).';

  if (fatal) return <p className="error">Backend not reachable: {fatal}</p>;
  if (!schema) return <p>Loading schema...</p>;
  return (
    <div className="layout">
      <header>
        <b>GATOR workbench</b><span className="hint"> {meta?.version} | {meta?.environment?.environment} | data-only outputs (no plots)</span>
        {/* The hand-edited settings.json is not valid JSON: the backend works on defaults and leaves the file alone. Said on a
            line of its own under the header, as /api/meta said it when the page opened - never hidden, not dismissable. */}
        {meta?.settings_problem && <p className="settings-problem warn">{meta.settings_problem}</p>}
        <span className="spacer" />
        <ValidationStatus validation={validation} config={config} schema={schema} />
        <button disabled={!!validation?.blocks_run || control.phase !== 'idle'} onClick={() => start(true)}
          title={control.phase === 'idle' ? 'ONE costed evaluation of the initial design. It is a preflight record, not free.' : 'Not while the header holds a run that is active or paused. Abort lets go of a paused run.'}>Single baseline simulation</button>
        <RunButtons control={control} blocked={!!validation?.blocks_run} onStart={() => start(false)} onResumed={started => showRun(started, 'resume')}
          onMessage={setMessage} onShow={dir => { setRunDir(dir); setTab('status'); }} />
      </header>
      {message && <div className={`banner ${message.level}`} onClick={() => setMessage(null)}>
        {/* A start refused by the check before every run: its steps say it all (what differs, what to do). */}
        {message.detail?.code === 'consistency' && message.detail.report?.steps ? <CheckSteps result={message.detail.report} refused />
          : <>{message.text}{(message.detail?.code || message.detail?.report) && <details onClick={e => e.stopPropagation()}><summary>Technical details</summary>
            <pre>{[message.detail.code && `code: ${message.detail.code}`, message.detail.report && JSON.stringify(message.detail.report, null, 1)].filter(Boolean).join('\n')}</pre></details>}</>}</div>}
      <aside className="left">
        <ConnectionButton profileId={profileId} setProfileId={(id, record) => setConfig((c: Json) => ({ ...c, run: { ...c.run, connection_profile_id: id } }), record)} />
        <CircuitPanel config={config} setConfig={setConfig} circuit={circuit} setCircuit={setCircuit} profileId={profileId}
          onAgent={(kind, selection, prompt) => { setAgentRequest({ kind, selection, prompt }); setTab('agent'); }} taskSlot={taskSlot} taskNotes={taskNotes}
          taskEpoch={taskEpoch} />
      </aside>
      <main>
        <Editors schema={schema} config={config} setConfig={setConfig} undo={store.undo} redo={store.redo} canUndo={store.canUndo} canRedo={store.canRedo}
          validation={validation} onAgent={(kind, selection) => { setAgentRequest({ kind, selection }); setTab('agent'); }} taskSlot={setTaskSlot} taskNotes={setTaskNotes} />
      </main>
      <aside className="right">
        <RunPanel schema={schema.json_schema} config={config} setConfig={setConfig} runs={runs} circuit={circuit} />
        <OutputPanel config={config} setConfig={setConfig} meta={meta} activeRun={status} />
        <ResearchPanel config={config} setConfig={setConfig} />
      </aside>
      <footer>
        <div className="tabs">
          {/* The agent tab carries a small control at its right end, where a browser tab has its close button: it moves the
              conversation into a window of its own. Two sibling buttons in one tab shape - a button inside a button is not valid. */}
          <span className={`tab-group${tab === 'agent' ? ' active' : ''}${agentDetached ? ' detached' : ''}`}>
            <button onClick={() => setTab('agent')}>Agent</button><span className="tab-slot" ref={setAgentTabSlot} /></span>
          {(['status', 'logs', 'data', 'files', 'corners'] as Exclude<BottomTab, 'agent'>[]).map(t => <button key={t} className={t === tab ? 'active' : ''} onClick={() => setTab(t)}>
            {{ status: 'Run status', logs: 'Logs', data: 'Data tables', files: 'Output files', corners: 'Corner check' }[t]}</button>)}
          <span className="spacer" />
          <RunListButton runs={runs} runsError={runsError} runDir={runDir} status={status} onChoose={setRunDir} onRefresh={refreshRuns} />
        </div>
        <div className="bottom-body">
          <AgentTab hidden={tab !== 'agent'} config={config} setConfig={setConfig} request={agentRequest} clearRequest={() => setAgentRequest(null)}
            tabSlot={agentTabSlot} onDetached={setAgentDetached} runDir={runDir} runActive={!!status?.worker_alive} />
          {tab === 'status' && <StatusTab status={status} runDir={runDir} error={statusError} onContinue={continueRun} continueBlocked={continueBlocked} />}
          {tab === 'logs' && <LogsTab runDir={runDir} alive={!!status?.worker_alive} />}
          {tab === 'data' && <DataTab runDir={runDir} status={status} />}
          {tab === 'files' && <FilesTab runDir={runDir} />}
          {tab === 'corners' && <CornerCheckTab runDir={runDir} />}
        </div>
      </footer>
    </div>
  );
}
