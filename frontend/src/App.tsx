import { CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError, Json, NO_ANSWER, plainError, saveJson } from './api';
import { Look, LOOK_NAMES, setLook, useLook } from './theme';
import { Icon } from './panels/Icons';
import { setUnitForms } from './units';
import { rowsFrom, useConfig, usePolling, useRequest, useTaskSaves } from './store';
import { CircuitPanel } from './panels/Left';
import { ConnectionButton } from './panels/Connection';
import { CheckSteps } from './panels/Consistency';
import { Editors } from './panels/Editors';
import { ValidationStatus } from './panels/Issues';
import { RunButtons } from './panels/RunControl';
import { changesByItself, isLive, RESUMABLE, useRunControl } from './runState';
import { HEADER_RUN_KEY, SHOWN_RUN_KEY } from './contract';
import { CALIBRATION_DESIGNS, launchKept, useLaunchActions } from './launch';
import { LaunchRefusal } from './panels/LaunchRefusal';
import { useRunBrief } from './panels/RunBrief';
import { RunPanel } from './panels/Right';
import { OutputPanel } from './panels/OutputPanel';
import { ResearchPanel } from './panels/ResearchPanel';
import { folderName } from './format';
import { APPLY_AND_SAVE } from './panels/calibrationPlan';
import { TASK_BASELINE_STARTED } from './panels/TaskSave';
import { CrashPanel } from './panels/CrashPanel';
import { BottomPanel, type BottomTab, useBottomPanel } from './panels/BottomPanel';
import { useCalibrationOffer } from './page/calibrationOffer';
import { useRunWindowActions } from './page/runWindowActions';
import { useNewest } from './newest';
import { keep, oncePerBrowser, readKept } from './kept';


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

/** The header's look switch (record 7.158): Whiteprint by day, Silicon Night by night. An icon, like the run buttons. */
function LookSwitch() {
  const look = useLook();
  const other: Look = look === 'silicon' ? 'whiteprint' : 'silicon';
  return <button className="look-switch" aria-pressed={look === 'silicon'} onClick={() => setLook(other)}
    title={`Switch look: now ${LOOK_NAMES[look]}; press for ${LOOK_NAMES[other]}. Kept in this browser; the pop-up windows follow.`}>
    <Icon name={look === 'silicon' ? 'sun' : 'moon'} label="Switch look" /></button>;
}

/** The run the bottom tabs show, kept in this browser (SHOWN_RUN_KEY) with the header's run of that moment (record 7.212): a page loaded
 *  again shows the run it showed - or none, after a task without runs was chosen. Unless the header holds another run by
 *  then (started in another tab of the page, say): the page opens on the header's run then, as it always did, and so does a
 *  browser that never kept one. */
const shownRun = (): string | null => readKept(s => {
  const header = s.getItem(HEADER_RUN_KEY) || null, kept = JSON.parse(s.getItem(SHOWN_RUN_KEY) ?? 'null');
  return kept && typeof kept === 'object' && (kept.header ?? null) === header ? kept.run ?? null : header;
}, () => null);

/** Layout (specification section 2): left = project, connection, circuit; center = three editors;
 *  right = run configuration + output settings (always visible); bottom = status, logs, data, files, training, corner check,
 *  with the Agent window and the run window opened from its tab line (record 7.253: the Agent tab became "Agent...", drawn
 *  as a tab but opening a window - no tab view).
 *  Tables, numbers, status and file lists. On screen only, by user decision: two pictures of the circuit - the graph view
 *  (2026-09-21) and the circuit picture in the left column (2026-10-03) - and the Training tab's charts of a run's
 *  recorded numbers (2026-10-05, record 7.193); nothing drawn is written. */
/** The page under its crash panel (record 7.188, design advice): the configuration and its Undo history live above the panel,
 *  so a failure to draw any part of the page - this function's own work included - is shown with Undo, Export JSON and Reload
 *  instead of a blank page, and Undo draws the page again from the configuration before the last change. */
export function App() {
  const store = useConfig();
  return <CrashPanel undo={store.undo} canUndo={store.canUndo} config={store.config}><Page store={store} /></CrashPanel>;
}

function Page({ store }: { store: ReturnType<typeof useConfig> }) {
  const { config, setConfig } = store;
  const [schema, setSchema] = useState<Json>(null);
  const [meta, setMeta] = useState<Json>(null);
  const [circuit, setCircuit] = useState<Json>(null);
  const [runs, setRuns] = useState<Json[]>(NO_RUNS);
  const [runsError, setRunsError] = useState<string | null>(null);   // the run list could not be read: said, not shown as "no run yet"
  const [runDir, setRunDir] = useState<string | null>(shownRun);
  const [tab, setTab] = useState<BottomTab>('status');
  const panel = useBottomPanel(runDir);
  const { bottom, folded, unfold, layoutRef } = panel;
  const [titleSlot, setTitleSlot] = useState<HTMLElement | null>(null);            // the header's title block: the circuit panel puts the task's facts there
  const [taskSlot, setTaskSlot] = useState<HTMLElement | null>(null);              // editors' tab line: where the circuit panel puts "Save task"
  const [taskNotes, setTaskNotes] = useState<HTMLElement | null>(null);            // under the editors' toolbar: its messages and questions
  const [message, setMessage] = useState<Json>(null);
  // Two output defaults changed (record 7.280): a save point every 200 evaluations (50 before) and the data tables written
  // every 64 (16 before). A draft keeps the values it was made with, so, once per browser, a draft that still holds an old
  // default exactly gets the new one - as one Undo step, and said; a value chosen otherwise is kept.
  useEffect(() => {
    if (!oncePerBrowser('gator-workbench-output-defaults-2026-10-08')) return;   // without lasting storage a value the user restored would be changed again
    const out = config.output ?? {};
    const saves = out.checkpoint_every_evaluations === 50 && out.checkpoint_every_seconds == null, tables = out.flush_every_evaluations === 16;
    if (!saves && !tables) return;
    setConfig((c: Json) => ({ ...c, output: { ...c.output, ...(saves ? { checkpoint_every_evaluations: 200 } : {}),
      ...(tables ? { flush_every_evaluations: 64 } : {}) } }));
    setMessage({ level: 'info', text: `Updated to the new defaults (record 7.280): ${[saves && 'a save point every 200 evaluations (was 50)',
      tables && 'the data tables written every 64 evaluations (was 16)'].filter(Boolean).join(' and ')}. Undo restores the old values.` });
  }, []);
  const [fatal, setFatal] = useState<string | null>(null);
  const profileId: string | null = config.run.connection_profile_id ?? null;

  useEffect(() => {
    Promise.all([api.schema(), api.meta()]).then(([s, m]) => {
      setUnitForms(s.unit_forms);                    // how quantities are written and read (record 7.208)
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
  const listing = useNewest();
  // One function for the whole page (useCallback; the output root through a ref), so the panels that take it are not drawn
  // again at every status update (record 7.275). A list that is the same as the one held keeps that array: what depends
  // on the runs (the saved models, the Training tab) is not asked again for nothing. `fresh`: the backend reads every
  // run folder anew (Refresh list; record 7.274).
  const outputRoot = useRef(config.output.output_root);
  outputRoot.current = config.output.output_root;
  const readRuns = useCallback((fresh = false): Promise<{ list: Json[]; error: string | null }> => {
    const mine = listing.next();
    return api.runs(outputRoot.current ?? undefined, fresh).then(r => ({ list: r.runs as Json[], error: null }), e => ({ list: NO_RUNS, error: plainError(e) }))
      .then(read => {
        if (mine()) { setRuns(held => (JSON.stringify(held) === JSON.stringify(read.list) ? held : read.list)); setRunsError(read.error); }
        return read;
      });
  }, []);
  const refreshRuns = useCallback((fresh = false): Promise<Json[]> => readRuns(fresh).then(read => read.list), [readRuns]);

  // Debounce validation and ignore replies for a configuration that has since changed. `sent`: the configuration the
  // report is about - its row paths (targets[3]) name rows of THAT configuration, which Delete, Undo or Import may have
  // moved by the time it is drawn (the editors check the row before they mark it). Asked again after a save of the task too
  // (record 7.222): the rows may not change, but what they are compared with did.
  const configKey = useMemo(() => JSON.stringify(config), [config]);
  const taskSaves = useTaskSaves();
  const validationRead = useRequest<Json>(signal => api.validate(config, signal, rowsFrom(config.circuit?.task_id)).catch(rejected).then(v => ({ ...v, sent: config })), [configKey, taskSaves],
    { delay: 500, keepPrevious: true });
  const validation = useMemo(() => validationRead.error ? { blocks_run: true, issues: [{ level: 'error', code: 'no_answer', path: '', message: validationRead.error }], facts: {} }
    : validationRead.value, [validationRead.value, validationRead.error]);

  // How often the run shown is read: see the effect after useRunControl below.
  const [statusEvery, setStatusEvery] = useState(1500);
  // The run shown is gone (deleted, or outside the allowed roots by now - it may be the remembered one the page opened
  // with): it is let go, as the header lets go of its own, instead of being asked for every 1.5 s for ever while the strip
  // still names its folder. Two answers in a row: on the 9p-mounted D: drive a stat right after a rename can fail once,
  // and one 404 of a run that is there must not take it off the page.
  const gone = useRef(0);
  useEffect(() => { gone.current = 0; }, [runDir]);
  const readStatus = (dir: string, signal: AbortSignal) => api.status(dir, signal).then(value => { gone.current = 0; return value; }, e => {
    if (e instanceof ApiError && (e.status === 403 || e.status === 404) && ++gone.current >= 2) setRunDir(shown => (shown === dir ? null : shown));
    throw e;
  });
  const { value: polledStatus, error: statusError } = usePolling(signal => readStatus(runDir!, signal), statusEvery, !!runDir, [runDir]);
  const status = polledStatus?.run_dir === runDir ? polledStatus : null;
  // Corner check only where corners can be used (record 7.182, design advice): the loaded circuit simulates at corners, or the run
  // shown is MOCK (its corners are analytic). No registered circuit does since 2026-09-30 (record 7.128); the tab comes back by
  // itself with one that does.
  const cornersUsable = circuit?.training_capabilities?.corners === true || !!status?.manifest?.mock;
  useEffect(() => { if (tab === 'corners' && !cornersUsable) setTab('status'); }, [tab, cornersUsable]);
  const isReal = circuit?.loaded && circuit.mock === false;
  // The run the header buttons act on (Start -> Pause -> Resume, Abort). It is not the run the bottom tabs show.
  const [looked, setLooked] = useState(false);
  const control = useRunControl(status, looked);
  // The run shown, kept with the header's run (shownRun above); again when the header takes or lets go of one.
  useEffect(() => {
    keep(s => s.setItem(SHOWN_RUN_KEY, JSON.stringify({ run: runDir, header: control.dir })));   // a private window: not kept
  }, [runDir, control.dir]);
  const { calibrated, calibrationOffer, calibrationReady, answerCalibration } = useCalibrationOffer({ control, config, setConfig, setMessage });
  // The run shown is read every 1.5 s while it can change by itself: a worker is alive, its state is a live one, or the
  // header is starting, resuming, pausing or ending a run. Otherwise it waits for a press on this page: every 15 s while
  // it could still be continued (paused, stopped, interrupted - another browser may continue it), once a minute once it
  // has ended for good (completed, failed, cancelled). Until 2026-09-30 a paused or stopped run was read every 1.5 s, and
  // each read re-reads its tables. The header's phase counts only when the header's run IS the run shown (record 7.125:
  // a finished run in the tabs was read every 1.5 s while the header paused or aborted another one).
  const transitional = control.dir === runDir && ['starting', 'resuming', 'pausing', 'aborting', 'finishing'].includes(control.phase);
  useEffect(() => setStatusEvery(changesByItself(status, transitional) ? 1500
    : ['completed', 'failed', 'cancelled'].includes(status.state) ? 60000 : 15000), [status?.worker_alive, status?.state, transitional]);
  // When the header's run comes to rest, the Project column reads its task again (a finished Baseline simulation
  // records the task's reference by itself, status record 7.78): a counter the column follows. Not on the page's first look,
  // and not after a start that never ran (refused or declined) or a paused run let go: nothing about the task changed.
  const [taskEpoch, setTaskEpoch] = useState(0);
  const lastPhase = useRef(control.phase);
  useEffect(() => {
    if (control.phase === 'idle' && ['starting', 'resuming', 'running', 'pausing', 'aborting', 'finishing'].includes(lastPhase.current)) setTaskEpoch(n => n + 1);
    lastPhase.current = control.phase;
  }, [control.phase]);
  const adopted = useRef(false);
  const controlNow = useRef(control);              // the header as it is when the list arrives (a launch recovered after a reload may hold one by then)
  controlNow.current = control;
  useEffect(() => {
    // The list follows the output root while it is typed: read 1 s after the last keystroke, not once per key (each read
    // looks at every run under the root; record 7.275). The first read, when the page opens, goes at once.
    const timer = setTimeout(() => refreshRuns().then(list => {
      // Once, when the page opens: a run that is live although this page does not hold it (started from another browser or
      // the CLI, or the browser's memory was cleared) is taken over, so the header offers Pause and Abort, not a second Start.
      if (adopted.current) return;
      adopted.current = true;
      const header = controlNow.current;
      const running = list.some(r => r.run_dir === header.dir && isLive(r)) ? null : list.find(isLive);
      if (running) {
        // Said (record 7.261), with the paused run the header held: it stays paused, and Runs continues it.
        const resting = list.find(r => r.run_dir === header.dir && RESUMABLE.includes(r.state));
        header.take(running.run_dir); setRunDir(running.run_dir);
        // A launch of this tab sent before a reload may have made it: the launcher says so once it has asked.
        const where = launchKept() ? 'a live run' : 'a live run started elsewhere (another browser tab, the command line or a task\'s baseline)';
        setMessage({ level: 'info', text: `The header took over ${folderName(running.run_dir)}, ${where}: its Pause and Abort act on it.`
          + (resting ? ` ${folderName(resting.run_dir)} stays paused; continue it from Runs.` : '') });
      }
      setLooked(true);
    }), adopted.current ? 1000 : 0);
    return () => clearTimeout(timer);
  }, [config.output.output_root]);
  // The bottom tabs follow the registered task (record 7.212, user: "after selecting specific task, it automatically load the
  // most recent corresponding run of the registered task. If there is no recent run, then leave run selection and run status
  // default blank unless you choose other runs"). When the page's task changes - chosen under Task, saved for the first time,
  // a choice taken back with Undo - the run list is read again and the task's newest run is shown (a Baseline simulation is
  // one of its runs), or no run. Not when the page opens: the run it showed is kept. A run chosen in the run window or
  // started while the list is read stays, and so does the run shown when the read fails or the page leaves its tasks for a
  // Virtuoso cell. The header's Start / Pause / Abort keep their own run. A server older than this page lists runs without
  // their task: the run shown stays then, instead of every choice showing none.
  const taskKey: string | null = config.circuit?.source === 'registered_task' ? config.circuit.task_id ?? null : null;
  const followedTask = useRef(taskKey);
  // The generation of the Runs window's Load run / New run like this (record 7.270, Astra's review of 2026-10-07): each one
  // takes the next number and goes on only while it is still the newest - a task chosen elsewhere lets it go too.
  const loadSerial = useNewest();
  const shownNow = useRef(runDir);
  shownNow.current = runDir;
  useEffect(() => {
    if (taskKey === followedTask.current) return;
    followedTask.current = taskKey;
    loadSerial.drop();                                   // a task chosen elsewhere: a Load run still on its way is let go
    if (!taskKey) return;
    const before = shownNow.current;
    readRuns().then(({ list, error }) => {
      if (error || followedTask.current !== taskKey || shownNow.current !== before) return;
      if (list.length && !list.some(r => 'task_key' in r)) return;
      setRunDir(list.find(r => r.task_key === taskKey)?.run_dir ?? null);
    });
  }, [taskKey]);

  const showRun = (started: Json, as: 'start' | 'resume', note = '') => {
    setRunDir(started.run_dir); setTab('status'); unfold(); refreshRuns();
    const said = note ? ` ${note}` : '';
    setMessage(as === 'resume' ? { level: 'info', text: `Continuing in the original run directory: ${started.run_dir}${said}` }
      : { level: started.mock ? 'mock' : 'info', text: `${started.mock ? started.mock_notice + ' ' : ''}Run directory: ${started.run_dir}${said}` });
  };
  // On success the run becomes the header's run and the shown run, in one place, and the message names it (record 7.261);
  // a paused run the header lets go of for it is named too - it stays paused, and Runs continues it.
  const launchedRun = (started: Json, as: 'start' | 'resume', note?: string) => {
    const resting = control.dir && control.dir !== started.run_dir && RESUMABLE.includes(control.status?.state) ? control.dir : null;
    control.take(started.run_dir, as);
    showRun(started, as, [note, resting && `${folderName(resting)} stays paused; continue it from Runs.`].filter(Boolean).join(' '));
  };
  // A task's baseline simulation, started by Save task (TaskSave.tsx), is taken into the header only when the header is free
  // or holds a run at rest (record 7.261): it used to replace a paused run without a word, and a live one too. A header that
  // holds no run is free while the page still reads the run list ("checking").
  const adoptBaseline = (started: Json) => {
    if (!control.dir || control.phase === 'idle' || control.phase === 'paused') { launchedRun(started, 'start', "The task's baseline simulation has started."); return; }
    refreshRuns();
    setMessage({ level: 'info', text: `The task's baseline simulation runs as ${folderName(started.run_dir)}; the header keeps its own run. The baseline is under Runs.` });
  };
  const automaticRun = useRef(adoptBaseline);
  automaticRun.current = adoptBaseline;
  useEffect(() => {
    const started = (event: Event) => automaticRun.current((event as CustomEvent<Json>).detail);
    window.addEventListener(TASK_BASELINE_STARTED, started);
    return () => window.removeEventListener(TASK_BASELINE_STARTED, started);
  }, []);

  // The run brief (record 7.264): the header's run chip opens it; Show results there does what the chip's press did.
  const brief = useRunBrief({ control, runs, onRefreshRuns: refreshRuns, onShow: dir => { setRunDir(dir); setTab('status'); unfold(); } });

  // ---- the launcher (record 7.261, launch.ts): Start, Calibration, Resume and Continue -------------------------------------
  const { launcher, shownCheck, startBlocked, setNextModel, nextLine, resumeBlocked, continueBlocked, headerRefusal, shownRefusal, start,
    continueShown, resumeHeld, fineTuneFrom } = useLaunchActions({ control, meta, config, setConfig, configKey, validation, runDir, status, circuit,
    isReal: !!isReal, launchedRun, setMessage });

  // ---- the Runs window's actions (record 7.267; plan "Load run" and "Existing runs: continued in place"): page/runWindowActions.ts
  const { taskLoad, askContinue, runWindow } = useRunWindowActions({ config, setConfig, runs, taskKey, followedTask, loadSerial, setMessage, setRunDir, setTab, unfold });

  if (fatal) return <p className="error">Backend not reachable: {fatal}</p>;
  if (!schema) return <p>Loading schema...</p>;
  return (
    <div className={`layout${folded ? ' bottom-folded' : ''}`} ref={layoutRef} style={bottom.height ? { '--foot': `${bottom.height}px` } as CSSProperties : undefined}>
      <header>
        {/* The title block (record 7.158): the page names what it works on - the task's facts come from the circuit panel. The
            version and the environment are one hover away, on the name. */}
        <div className="title-block">
          <span className="tb-brand" title={`GATOR workbench ${meta?.version ?? ''} | ${meta?.environment?.environment ?? ''} | data-only outputs (no plots)`}>
            <b>GATOR</b><span className="tb-sub">workbench</span></span>
          <LookSwitch />
          <span className="tb-facts" ref={setTitleSlot} />
          {/* The Connection button in the title block (record 7.182, user: "move the conection button to the header"): its name
              over the connection and its state, as the cells beside it; it opens the connection window as before. */}
          <ConnectionButton profileId={profileId} setProfileId={(id, record) => setConfig((c: Json) => ({ ...c, run: { ...c.run, connection_profile_id: id } }), record)} />
        </div>
        {/* The hand-edited settings.json is not valid JSON: the backend works on defaults and leaves the file alone. Said on a
            line of its own under the header, as /api/meta said it when the page opened - never hidden, not dismissable. */}
        {meta?.settings_problem && <p className="settings-problem warn">{meta.settings_problem}</p>}
        {store.saveError && <div className="settings-problem persistence-problem error" role="alert">
          <span>{store.saveError}</span><button onClick={store.retrySave}>Retry save</button>
          <button onClick={() => saveJson(`${config.project.task_name || 'configuration'}.json`, config)}>Export JSON</button>
        </div>}
        {/* "Calibration ready" (record 7.204): the Calibration run the header holds has ended. A line of its own under the
            header, like the two above; it goes when it is answered, when the page holds the values, or with the next run. */}
        {/* A refusal of Start, Calibration or Resume (record 7.261): it stays on a line of its own until what it depends on
            changes - the configuration, or the header's run - or it is closed. */}
        {headerRefusal && <LaunchRefusal refusal={headerRefusal} onDismiss={() => launcher.setRefusal(null)} />}
        {calibrationReady && calibrationOffer && <div className="calibration-ready" role="status">
          {calibrated.status === 'calibrated'
            ? <><span><b>Calibration ready</b>{calibrated.task_key ? ` for ${calibrated.task_key}` : ''}: {calibrationOffer.values}. <span className="hint">Proposed
                from {calibrated.designs?.scored} random designs; nothing has changed yet. The table is under Run status.</span></span>
              {calibrationOffer.saves
                ? <><button className="primary" onClick={() => answerCalibration('save')} title={`Apply and save: Writes ${calibrationOffer.what} into the page, as one Undo step, ${APPLY_AND_SAVE}`}>Apply and save</button>
                    <button onClick={() => answerCalibration('apply')} title={`Apply only: Writes ${calibrationOffer.what} into the page, as one Undo step. Nothing is simulated and no task is saved.${calibrationOffer.afterwards}`}>Apply only</button></>
                : <button onClick={() => answerCalibration('apply')} title={`Apply calibration: Writes ${calibrationOffer.what} into the page, as one Undo step. Nothing is simulated and no task is saved.${calibrationOffer.afterwards}`}>Apply calibration</button>}
              <button onClick={() => answerCalibration('no')} title="Not now: Leaves everything as it is. The proposals stay under Run status of this run, with Apply calibration.">Not now</button></>
            : <><span><b>Calibration finished:</b> nothing is proposed. {calibrated.reason}</span>
              <button onClick={() => answerCalibration('no')} title="Closes this line. The run's numbers stay under Run status.">OK</button></>}
        </div>}
        <span className="spacer" />
        <ValidationStatus validation={validation} config={config} schema={schema} />
        <button disabled={!!startBlocked} onClick={() => start(true)}
          title={startBlocked ? `Calibration: ${startBlocked}`
            : `${CALIBRATION_DESIGNS} random designs over the Parameters ranges, each costed. No starting-design baseline. `
              + 'Proposes a Scale for each Specs row and the Initial alpha; Run status shows them with Apply, nothing changes by itself.'}>Calibration</button>
        <RunButtons control={control} startBlocked={startBlocked} resumeBlocked={resumeBlocked} onStart={() => start(false)} onResume={resumeHeld}
          onMessage={setMessage} onChip={brief.open} next={nextLine} />
        {brief.element}
      </header>
      {message && <div className={`banner ${message.level}`} onClick={() => setMessage(null)}>
        {/* A start refused by the check before every run: its steps say it all (what differs, what to do). */}
        {message.detail?.code === 'consistency' && message.detail.report?.steps ? <CheckSteps result={message.detail.report} refused />
          : <>{message.text}{(message.detail?.code || message.detail?.report) && <details onClick={e => e.stopPropagation()}><summary>Technical details</summary>
            <pre>{[message.detail.code && `code: ${message.detail.code}`, message.detail.report && JSON.stringify(message.detail.report, null, 1)].filter(Boolean).join('\n')}</pre></details>}</>}</div>}
      <aside className="left">
        <CircuitPanel config={config} setConfig={setConfig} circuit={circuit} setCircuit={setCircuit} profileId={profileId}
          taskSlot={taskSlot} taskNotes={taskNotes} titleSlot={titleSlot}
          taskEpoch={taskEpoch} runs={runs} refreshRuns={refreshRuns} taskLoad={taskLoad} />
      </aside>
      <main>
        <Editors schema={schema} config={config} setConfig={setConfig} undo={store.undo} redo={store.redo} canUndo={store.canUndo} canRedo={store.canRedo}
          validation={validation} taskSlot={setTaskSlot} taskNotes={setTaskNotes} />
      </main>
      <aside className="right">
        <RunPanel schema={schema.json_schema} config={config} setConfig={setConfig} runs={runs} circuit={circuit} onNext={setNextModel} />
        <OutputPanel config={config} setConfig={setConfig} meta={meta} activeRun={status} />
        <ResearchPanel config={config} setConfig={setConfig} />
      </aside>
      <BottomPanel panel={panel} tab={tab} setTab={setTab} cornersUsable={cornersUsable} config={config} setConfig={setConfig} runs={runs} runsError={runsError}
        runDir={runDir} status={status} statusError={statusError} runWindow={runWindow} refreshRuns={refreshRuns} shownCheck={shownCheck}
        continueBlocked={continueBlocked} shownRefusal={shownRefusal} continueShown={continueShown} launcher={launcher} fineTuneFrom={fineTuneFrom}
        askContinue={askContinue} />
    </div>
  );
}
